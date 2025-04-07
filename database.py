import sqlite3
import numpy as np
import pickle
import face_recognition
import os

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('users.db', check_same_thread=False)
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            face_encoding BLOB NOT NULL,
            image_path TEXT
        )
        ''')
        self.conn.commit()

    def register_user(self, name, roll_no, face_encoding, image_path=None):
        cursor = self.conn.cursor()
        encoding_blob = pickle.dumps(face_encoding)
        cursor.execute('''
        INSERT INTO users (name, roll_no, face_encoding, image_path)
        VALUES (?, ?, ?, ?)
        ''', (name, roll_no, encoding_blob, image_path))
        self.conn.commit()

    def find_face_matches(self, face_encoding):
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, roll_no, face_encoding FROM users')
        for row in cursor.fetchall():
            stored_encoding = pickle.loads(row[2])
            if face_recognition.compare_faces([stored_encoding], face_encoding)[0]:
                return row[0], row[1]  # Return name and roll_no
        return None

    def delete_user_by_roll_no(self, roll_no):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM users WHERE roll_no = ?', (roll_no,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_user_image_path(self, roll_no):
        cursor = self.conn.cursor()
        cursor.execute('SELECT image_path FROM users WHERE roll_no = ?', (roll_no,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_all_face_records(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, roll_no, image_path FROM users ORDER BY name')
        return cursor.fetchall()

    def get_face_count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]

    def delete_face_record(self, roll_no):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM users WHERE roll_no = ?', (roll_no,))
        self.conn.commit()
        return cursor.rowcount > 0

    def cleanup_orphaned_images(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT image_path FROM users WHERE image_path IS NOT NULL')
        db_images = {row[0] for row in cursor.fetchall()}
        
        folder_images = set()
        recognized_faces_dir = 'static/recognized_faces'
        if os.path.exists(recognized_faces_dir):
            for filename in os.listdir(recognized_faces_dir):
                if filename.endswith('.jpg'):
                    filepath = os.path.join(recognized_faces_dir, filename)
                    folder_images.add(filepath)
        
        for image_path in folder_images - db_images:
            try:
                os.remove(image_path)
                print(f"Deleted orphaned image: {image_path}")
            except Exception as e:
                print(f"Error deleting orphaned image {image_path}: {e}")

    def cleanup_orphaned_records(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, image_path FROM users WHERE image_path IS NOT NULL')
        
        deleted_count = 0
        for row in cursor.fetchall():
            if not os.path.exists(row[1]):
                cursor.execute('DELETE FROM users WHERE id = ?', (row[0],))
                deleted_count += 1
        
        if deleted_count > 0:
            self.conn.commit()
            print(f"Deleted {deleted_count} orphaned records")