document.addEventListener('DOMContentLoaded', () => {
    const registrationPanel = document.getElementById('registration-form');
    const faceRegisterForm = document.getElementById('face-register-form');
    const cancelBtn = document.getElementById('cancel-registration');
    const statusDisplay = document.getElementById('detection-status');
    const notification = document.getElementById('notification');
    const speakButtonContainer = document.getElementById('speak-button-container');
    const speakNameBtn = document.getElementById('speak-name-btn');
    const synth = window.speechSynthesis;
    
    let isRegistering = false;
    let currentFaceDetected = false;
    let lastRecognitionStatus = false;
    let lastSpokenTime = 0;
    const speakCooldown = 3000; // 3 seconds cooldown

    const showAlert = (message, type = 'success') => {
        notification.textContent = message;
        notification.className = `notification show ${type}`;
        setTimeout(() => notification.classList.remove('show'), 3000);
    };

    const speakName = (name) => {
        const now = Date.now();
        if (now - lastSpokenTime < speakCooldown) return;
        
        if (synth.speaking) {
            synth.cancel();
        }
        
        const utterance = new SpeechSynthesisUtterance(name);
        utterance.rate = 0.9;
        synth.speak(utterance);
        lastSpokenTime = now;
    };

    speakNameBtn.addEventListener('click', () => {
        if (lastRecognitionStatus && currentFaceDetected) {
            const name = statusDisplay.textContent.split(' (')[0]; // Extract name without roll number
            speakName(name);
        }
    });

    const updateStatus = (message, recognized = false) => {
        statusDisplay.textContent = message;
        statusDisplay.className = `status-badge ${recognized ? 'recognized' : 'unrecognized'}`;

        // Show/hide speak button based on recognition status
        if (recognized) {
            speakButtonContainer.style.display = 'block';
        } else {
            speakButtonContainer.style.display = 'none';
        }

        if (!recognized && !isRegistering && currentFaceDetected && !lastRecognitionStatus) {
            registrationPanel.classList.remove('hidden');
            isRegistering = true;
        } else if (recognized || !currentFaceDetected) {
            registrationPanel.classList.add('hidden');
            isRegistering = false;
        }

        lastRecognitionStatus = recognized;
    };

    faceRegisterForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const userData = {
            name: document.getElementById('name').value,
            roll_no: document.getElementById('roll-no').value,
            admin_mode: window.adminMode
        };

        try {
            const response = await fetch('/register_face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(userData)
            });

            const result = await response.json();
            
            if (result.success) {
                if (result.redirect) {
                    window.location.href = result.redirect;
                } else {
                    showAlert('Face registered successfully!');
                    registrationPanel.classList.add('hidden');
                    faceRegisterForm.reset();
                    isRegistering = false;
                    lastRecognitionStatus = true;
                }
            } else {
                showAlert('Registration failed. Please try again.', 'error');
            }
        } catch (error) {
            showAlert('Network error. Please try again.', 'error');
            console.error('Registration error:', error);
        }
    });

    cancelBtn.addEventListener('click', () => {
        registrationPanel.classList.add('hidden');
        faceRegisterForm.reset();
        isRegistering = false;
    });

    const checkFaceDetection = () => {
        fetch('/face_status')
        .then(response => response.json())
        .then(data => {
            currentFaceDetected = data.face_detected;
            updateStatus(
                data.face_detected
                ? (data.recognized ? data.name : 'Unknown Face Detected')
                : 'No Face Detected',
                data.recognized
            );
        })
        .catch(error => {
            console.error('Status check error:', error);
        });
    };

    setInterval(checkFaceDetection, 500);
});