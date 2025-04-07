from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import functools
import cv2
import numpy as np
import sqlite3
import face_recognition
from ultralytics import YOLO
from camera import Camera
from database import Database
import os
from datetime import datetime

# Initialize components globally
camera = None
db = None
yolo_model = None

def init_components():
    global camera, db, yolo_model
    if camera is None:
        camera = Camera()
    if db is None:
        db = Database()
    if yolo_model is None:
        yolo_model = YOLO('yolov8n.pt')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production

# Admin credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD_HASH = generate_password_hash("securepassword123")

# Initialize components at startup
init_components()

# Admin authentication decorator
def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return view(**kwargs)
    return wrapped_view

# Main Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/face_detection')
def face_detection():
    admin_mode = request.args.get('admin') == 'true' and session.get('admin_logged_in')
    return render_template('face_detection.html', admin_mode=admin_mode)

@app.route('/object_detection')
def object_detection():
    return render_template('object_detection.html')

@app.route('/face_status')
def face_status():
    status = camera.get_current_face_status()
    return jsonify(status)

@app.route('/object_status')
def object_status():
    with camera.object_lock:
        objects = dict(camera.object_count)
    return jsonify({'objects': objects})

def generate_frames(camera_feed):
    while True:
        frame = camera_feed()
        if frame is not None:
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                      b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed_face')
def video_feed_face():
    return Response(generate_frames(lambda: camera.generate_frames_face(db)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_object')
def video_feed_object():
    return Response(generate_frames(lambda: camera.generate_frames_object(yolo_model)),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/register_face', methods=['POST'])
def register_face():
    data = request.get_json()
    name = data.get('name')
    roll_no = data.get('roll_no')
    face_encoding = camera.get_current_face_encoding()

    if face_encoding is not None:
        success, frame = camera.camera.read()
        if success:
            image_path = camera.save_recognized_face(frame, name, roll_no)
            db.register_user(name, roll_no, face_encoding, image_path)
            if data.get('admin_mode'):
                return jsonify({'success': True, 'redirect': url_for('face_records')})
            return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/delete_face', methods=['POST'])
def delete_face():
    data = request.get_json()
    roll_no = data.get('roll_no')
    if roll_no:
        success = camera.delete_face_data(db, roll_no)
        return jsonify({'success': success})
    return jsonify({'success': False})

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if email == ADMIN_EMAIL and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid credentials")
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/check-auth')
def check_admin_auth():
    return jsonify({'authenticated': session.get('admin_logged_in', False)})

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    face_count = db.get_face_count()
    return render_template('admin_dashboard.html', face_count=face_count, object_count=len(yolo_model.names))

@app.route('/admin/face-records')
@admin_required
def face_records():
    face_data = db.get_all_face_records()
    return render_template('face_records.html', faces=face_data)

@app.route('/admin/object-settings')
@admin_required
def object_settings():
    objects = list(yolo_model.names.values())
    return render_template('object_settings.html', objects=objects)

@app.route('/admin/search-face')
@admin_required
def search_face():
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify({'success': False, 'message': 'Empty search query'})
    
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT name, roll_no, image_path 
        FROM users 
        WHERE LOWER(name) LIKE ? OR LOWER(roll_no) LIKE ?
        LIMIT 1
    ''', (f'%{query}%', f'%{query}%'))
    
    result = cursor.fetchone()
    if result:
        return jsonify({
            'success': True,
            'record': {
                'name': result[0],
                'roll_no': result[1],
                'image_path': result[2]
            }
        })
    else:
        return jsonify({'success': False, 'message': 'No matching records found'})

@app.route('/admin/update-face/<roll_no>', methods=['PUT'])
@admin_required
def update_face_record(roll_no):
    try:
        name = request.form.get('name')
        photo = request.files.get('photo')
        
        # Update name in database
        cursor = db.conn.cursor()
        cursor.execute('UPDATE users SET name = ? WHERE roll_no = ?', (name, roll_no))
        db.conn.commit()
        
        # Update photo if provided
        if photo:
            # Delete old image if exists
            cursor.execute('SELECT image_path FROM users WHERE roll_no = ?', (roll_no,))
            old_image = cursor.fetchone()[0]
            if old_image:
                try:
                    os.remove(os.path.join('static/recognized_faces', old_image))
                except:
                    pass
            
            # Save new image
            filename = f"{name}_{roll_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            filepath = os.path.join('static/recognized_faces', filename)
            photo.save(filepath)
            
            # Update database with new image path
            cursor.execute('UPDATE users SET image_path = ? WHERE roll_no = ?', (filename, roll_no))
            db.conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/admin/delete-face/<roll_no>', methods=['DELETE'])
@admin_required
def delete_face_record(roll_no):
    if db.delete_face_record(roll_no):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/admin/add-object', methods=['POST'])
@admin_required
def add_object():
    data = request.get_json()
    new_object = data.get('object')
    # Add your logic to save the new object
    return jsonify({'success': True, 'message': 'Object added successfully'})

@app.route('/admin/remove-object', methods=['POST'])
@admin_required
def remove_object():
    data = request.get_json()
    object_to_remove = data.get('object')
    # Add your logic to remove the object
    return jsonify({'success': True, 'message': 'Object removed successfully'})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
