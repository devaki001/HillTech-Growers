// Main JavaScript functionality
document.addEventListener('DOMContentLoaded', function() {
    // Load user crops on page load
    loadUserCrops();
    
    // Refresh crops button
    const refreshCropsBtn = document.getElementById('refresh-crops-btn');
    if (refreshCropsBtn) {
        refreshCropsBtn.addEventListener('click', loadUserCrops);
    }
    // Water flow control functionality
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const flowStatus = document.getElementById('flow-status');

    if (startBtn && stopBtn && flowStatus) {
        let isFlowActive = false;

        startBtn.addEventListener('click', function() {
            isFlowActive = true;
            updateFlowStatus();

            // Send API request
            fetch('/api/water_control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ action: 'start' })
            })
            .then(response => response.json())
            .then(data => {
                console.log('Water flow started:', data);
            })
            .catch(error => {
                console.error('Error:', error);
                isFlowActive = false;
                updateFlowStatus();
            });
        });

        stopBtn.addEventListener('click', function() {
            isFlowActive = false;
            updateFlowStatus();

            // Send API request
            fetch('/api/water_control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ action: 'stop' })
            })
            .then(response => response.json())
            .then(data => {
                console.log('Water flow stopped:', data);
            })
            .catch(error => {
                console.error('Error:', error);
                isFlowActive = true;
                updateFlowStatus();
            });
        });

        function updateFlowStatus() {
            if (isFlowActive) {
                flowStatus.textContent = 'ACTIVE';
                flowStatus.className = 'status-indicator status-active';
                startBtn.disabled = true;
                stopBtn.disabled = false;
            } else {
                flowStatus.textContent = 'STOPPED';
                flowStatus.className = 'status-indicator status-stopped';
                startBtn.disabled = false;
                stopBtn.disabled = true;
            }
        }
    }

    // Auto-refresh data every 30 seconds
    if (window.location.pathname === '/dashboard') {
        setInterval(function() {
            // In a real application, you would fetch updated data here
            console.log('Auto-refreshing dashboard data...');
        }, 30000);
    }

    // Smooth scrolling for navigation
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add loading states to buttons
    document.querySelectorAll('button').forEach(button => {
        button.addEventListener('click', function() {
            if (!this.disabled) {
                this.style.opacity = '0.7';
                setTimeout(() => {
                    this.style.opacity = '1';
                }, 300);
            }
        });
    });
});

// Utility functions
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        z-index: 1000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;

    if (type === 'success') {
        notification.style.background = '#16a34a';
    } else if (type === 'error') {
        notification.style.background = '#dc2626';
    } else if (type === 'warning') {
        notification.style.background = '#f97316';
    } else {
        notification.style.background = '#2563eb';
    }

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);

    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Format numbers with appropriate units
function formatValue(value, unit) {
    if (typeof value === 'number') {
        return value.toFixed(1) + unit;
    }
    return value + unit;
}

// Update timestamp display
function updateTimestamp() {
    const timestampElements = document.querySelectorAll('.timestamp');
    const now = new Date();
    const timeString = now.toLocaleString();

    timestampElements.forEach(element => {
        element.textContent = timeString;
    });
}

// Initialize timestamp updates
if (document.querySelector('.timestamp')) {
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
}
// Water Flow Control (single source of truth)
document.addEventListener('DOMContentLoaded', () => {
  const card = document.getElementById('water-control');
  if (!card) return; // not on this page

  const crop     = card.dataset.crop || '';
  const startBtn = document.getElementById('start-btn');
  const stopBtn  = document.getElementById('stop-btn');
  const status   = document.getElementById('flow-status'); // .wf-status-pill
  const led      = document.getElementById('wf-led');
  const lastEl   = document.getElementById('wf-last');
  const errEl    = document.getElementById('wf-error');
  const connDot  = document.getElementById('wf-conn-dot');
  const connTxt  = document.getElementById('wf-conn-txt');

  const setUI = (running) => {
    status.classList.toggle('running', running);
    status.classList.toggle('stopped', !running);
    status.innerHTML = running ? '<i class="fas fa-play"></i> RUNNING'
                               : '<i class="fas fa-ban"></i> STOPPED';
    led?.classList.toggle('running', running);
    startBtn.disabled = running;
    stopBtn.disabled  = !running;
  };

  const send = async (action) => {
    errEl.hidden = true; errEl.textContent = '';
    try {
      const res = await fetch('/api/water_control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ crop, action })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status !== 'success') throw new Error(data.message || 'Request failed');

      lastEl.textContent = `Last action: ${action.toUpperCase()} • ${new Date().toLocaleTimeString()}`;
      connDot?.classList.add('online');
      if (connTxt) connTxt.textContent = 'Arduino: Online';
    } catch (e) {
      setUI(action !== 'start'); // revert
      errEl.textContent = `Error: ${e.message || 'Device not reachable'}`;
      errEl.hidden = false;
      connDot?.classList.remove('online');
      if (connTxt) connTxt.textContent = 'Arduino: Offline?';
    }
  };

  startBtn.addEventListener('click', () => { setUI(true);  send('start'); });
  stopBtn .addEventListener('click', () => { setUI(false); send('stop');  });
});

// Load user crops function
async function loadUserCrops() {
    const cropsListEl = document.getElementById('my-crops-list');
    if (!cropsListEl) return;
    
    try {
        const response = await fetch('/api/user_crops');
        const data = await response.json();
        
        if (data.crops && data.crops.length > 0) {
            cropsListEl.innerHTML = data.crops.map(crop => `
                <div class="crop-item">
                    <div class="crop-info">
                        <strong>${crop.crop_name}</strong><br>
                        <small>Soil: ${crop.soil_type} | Water: ${crop.water_requirement}mm</small><br>
                        <small>Started: ${crop.start_date} | Status: ${crop.status}</small>
                    </div>
                    <div class="crop-actions">
                        <button class="btn btn-sm btn-danger" onclick="removeCrop(${crop.id})">
                            <i class="fas fa-trash"></i> Remove
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            cropsListEl.innerHTML = '<p>No crops added yet. Add crops from the recommendations above.</p>';
        }
    } catch (error) {
        console.error('Error loading crops:', error);
        cropsListEl.innerHTML = '<p>Error loading crops. Please try again.</p>';
    }
}

// Remove crop function
async function removeCrop(cropId) {
    if (!confirm('Are you sure you want to remove this crop?')) return;
    
    try {
        const response = await fetch(`/api/remove_crop/${cropId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            loadUserCrops(); // Refresh the list
        } else {
            alert('Error removing crop: ' + data.message);
        }
    } catch (error) {
        console.error('Error removing crop:', error);
        alert('Error removing crop. Please try again.');
    }
}

