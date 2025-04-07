document.addEventListener('DOMContentLoaded', () => {
    const videoFeed = document.getElementById('video-feed');
    const objectsList = document.getElementById('objects-list');
    const totalCount = document.getElementById('total-count');
    
    // Speech synthesis for voice alerts
    const synth = window.speechSynthesis;
    let lastAlertTime = 0;
    const alertCooldown = 3000;
    
    // Store detected objects
    let detectedObjects = {};
    let lastUpdateTime = 0;
    
    // Function to speak detected objects
    function speakObjects() {
        const now = Date.now();
        if (now - lastAlertTime < alertCooldown) return;
        
        const objects = Object.keys(detectedObjects);
        if (objects.length === 0) return;
        
        let message;
        if (objects.length === 1) {
            message = `${objects[0]} detected`;
        } else {
            message = `Multiple objects detected: ${objects.join(', ')}`;
        }
        
        const utterance = new SpeechSynthesisUtterance(message);
        utterance.rate = 1.0;
        synth.speak(utterance);
        lastAlertTime = now;
    }
    
    // Function to update the object list display
    function updateObjectsDisplay() {
        const objects = Object.entries(detectedObjects);
        totalCount.textContent = objects.reduce((sum, [_, count]) => sum + count, 0);
        
        objectsList.innerHTML = '';
        objects.sort((a, b) => b[1] - a[1]);
        
        objects.forEach(([name, count]) => {
            const item = document.createElement('div');
            item.className = 'object-item';
            
            const nameSpan = document.createElement('span');
            nameSpan.className = 'object-name';
            nameSpan.textContent = name;
            
            const countSpan = document.createElement('span');
            countSpan.className = 'object-count';
            countSpan.textContent = count;
            
            item.appendChild(nameSpan);
            item.appendChild(countSpan);
            objectsList.appendChild(item);
        });
    }
    
    // Check for object updates periodically
    function checkForUpdates() {
        const now = Date.now();
        if (now - lastUpdateTime > 2000) { // Update every 2 seconds
            fetch('/object_status')
                .then(response => response.json())
                .then(data => {
                    detectedObjects = data.objects || {};
                    updateObjectsDisplay();
                    speakObjects();
                    lastUpdateTime = now;
                })
                .catch(error => {
                    console.error('Error fetching object status:', error);
                });
        }
        requestAnimationFrame(checkForUpdates);
    }
    
    // Start checking for updates
    checkForUpdates();
    
    // Handle video stream errors
    videoFeed.addEventListener('error', () => {
        console.error('Video stream error occurred');
        alert('Failed to start video stream. Please refresh the page.');
    });
    
    // Initial update
    updateObjectsDisplay();
});