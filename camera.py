import cv2
import numpy as np
import face_recognition
import time
import os
from datetime import datetime
from collections import defaultdict
from threading import Lock

class Camera:
    def __init__(self):
        self.camera = cv2.VideoCapture(0)
        self.current_face_encoding = None
        self.current_face_status = {
            'face_detected': False,
            'recognized': False,
            'name': None
        }
        self.frame_count = 0
        self.skip_frames = 2
        self.last_face_detection_time = 0
        self.face_detection_interval = 0.1
        self.registered_faces = set()

        # Object detection enhancements
        self.object_tracking = defaultdict(dict)
        self.object_count = defaultdict(int)
        self.last_voice_alert = defaultdict(float)
        self.object_lock = Lock()
        self.last_detection_time = 0
        self.detection_interval = 0.1

        # Camera settings
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camera.set(cv2.CAP_PROP_FPS, 30)

        self.recognized_faces_dir = 'static/recognized_faces'
        os.makedirs(self.recognized_faces_dir, exist_ok=True)
        self.load_existing_faces()

    def __del__(self):
        self.camera.release()

    def load_existing_faces(self):
        for filename in os.listdir(self.recognized_faces_dir):
            if filename.endswith('.jpg'):
                parts = filename.split('_')
                if len(parts) >= 2:
                    face_id = f"{parts[0]}_{parts[1]}"
                    self.registered_faces.add(face_id)

    def get_current_face_status(self):
        return self.current_face_status

    def save_recognized_face(self, frame, name, roll_no):
        face_id = f"{name}_{roll_no}"
        if face_id not in self.registered_faces:
            existing_image = self.find_existing_image(face_id)
            if existing_image:
                return existing_image
            
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{face_id}_{timestamp}.jpg"
            filepath = os.path.join(self.recognized_faces_dir, filename)
            cv2.imwrite(filepath, frame)
            self.registered_faces.add(face_id)
            return filename
        return None

    def find_existing_image(self, face_id):
        for filename in os.listdir(self.recognized_faces_dir):
            if filename.startswith(face_id):
                return filename
        return None

    def delete_face_data(self, db, roll_no):
        image_path = db.get_user_image_path(roll_no)
        db.delete_user_by_roll_no(roll_no)
        
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            return True
        return False

    def generate_frames_face(self, db):
        success, frame = self.camera.read()
        if not success:
            return None

        frame = cv2.flip(frame, 1)
        current_time = time.time()

        if self.frame_count % self.skip_frames == 0 and \
           current_time - self.last_face_detection_time >= self.face_detection_interval:
            
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame, model="hog")
            
            self.current_face_status['face_detected'] = len(face_locations) > 0
            self.current_face_status['recognized'] = False
            self.current_face_status['name'] = None

            if face_locations:
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations, num_jitters=1)
                
                for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                    self.current_face_encoding = face_encoding
                    matches = db.find_face_matches(face_encoding)
                    
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4

                    if matches:
                        name, roll_no = matches
                        face_id = f"{name}_{roll_no}"
                        
                        if not self.find_existing_image(face_id):
                            self.save_recognized_face(frame[top:bottom, left:right], name, roll_no)
                        
                        self.current_face_status['recognized'] = True
                        self.current_face_status['name'] = f"{name} ({roll_no})"
                        
                        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                        label = f"{name} ({roll_no})"
                        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        cv2.rectangle(frame, (left, top - 30), (left + label_size[0], top), (0, 255, 0), cv2.FILLED)
                        cv2.putText(frame, label, (left, top - 10),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    else:
                        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                        label_size = cv2.getTextSize("Unknown", cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        cv2.rectangle(frame, (left, top - 30), (left + label_size[0], top), (0, 0, 255), cv2.FILLED)
                        cv2.putText(frame, "Unknown", (left, top - 10),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            self.last_face_detection_time = current_time

        self.frame_count += 1
        return frame

    def generate_frames_object(self, model):
        success, frame = self.camera.read()
        if not success:
            return None

        frame = cv2.flip(frame, 1)
        current_time = time.time()

        if current_time - self.last_detection_time >= self.detection_interval:
            input_frame = cv2.resize(frame, (320, 320))
            results = model.track(input_frame, persist=True, conf=0.5, iou=0.45, verbose=False)
            
            with self.object_lock:
                self.object_count.clear()
            
            for result in results:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                track_ids = result.boxes.id.cpu().numpy().astype(int) if result.boxes.id is not None else None

                for i, (box, conf, cls_id) in enumerate(zip(boxes, confidences, class_ids)):
                    track_id = track_ids[i] if track_ids is not None else None
                    class_name = model.names[cls_id]
                    
                    # Scale coordinates back to original frame size
                    x1, y1, x2, y2 = box
                    x1 = int(x1 * frame.shape[1] / 320)
                    y1 = int(y1 * frame.shape[0] / 320)
                    x2 = int(x2 * frame.shape[1] / 320)
                    y2 = int(y2 * frame.shape[0] / 320)
                    
                    with self.object_lock:
                        self.object_count[class_name] += 1
                    
                    # Draw bounding box
                    color = (0, 255, 0)  # Green color for all detections
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Draw label with confidence and tracking ID
                    label = f"{class_name} {conf:.2f}"
                    if track_id is not None:
                        label += f" ID:{track_id}"
                    
                    # Improve label visibility
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                    cv2.rectangle(frame, (x1, y1 - 30), (x1 + label_size[0], y1), color, cv2.FILLED)
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            self.last_detection_time = current_time

        # Draw object counts
        with self.object_lock:
            current_counts = dict(self.object_count)

        total_objects = sum(current_counts.values())
        cv2.putText(frame, f"Total: {total_objects}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        for i, (class_name, count) in enumerate(current_counts.items(), start=1):
            cv2.putText(frame, f"{class_name}: {count}", (10, 30 + i * 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return frame

    def get_current_face_encoding(self):
        return self.current_face_encoding