// Alerts page functionality
document.addEventListener('DOMContentLoaded', function() {
    const filterTabs = document.querySelectorAll('.filter-tab');
    const alertCards = document.querySelectorAll('.alert-card');

    // Filter functionality
    filterTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const filter = this.dataset.filter;

            // Update active tab
            filterTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Filter alerts
            alertCards.forEach(card => {
                const category = card.dataset.category;

                if (filter === 'all' || category === filter) {
                    card.style.display = 'flex';
                    card.style.animation = 'fadeIn 0.3s ease';
                } else {
                    card.style.display = 'none';
                }
            });

            // Update URL without page reload
            const url = new URL(window.location);
            if (filter === 'all') {
                url.searchParams.delete('filter');
            } else {
                url.searchParams.set('filter', filter);
            }
            window.history.replaceState({}, '', url);
        });
    });

    // Initialize filter from URL parameter
    const urlParams = new URLSearchParams(window.location.search);
    const initialFilter = urlParams.get('filter') || 'all';
    const initialTab = document.querySelector(`[data-filter="${initialFilter}"]`);
    if (initialTab) {
        initialTab.click();
    }

    // Auto-refresh alerts every 60 seconds
    setInterval(function() {
        // In a real application, you would fetch updated alerts here
        console.log('Auto-refreshing alerts...');
        updateAlertTimestamps();
    }, 60000);

    // Mark alerts as read when clicked
    alertCards.forEach(card => {
        card.addEventListener('click', function() {
            this.style.opacity = '0.7';
            this.classList.add('read');

            // In a real application, you would send a request to mark as read
            setTimeout(() => {
                this.style.opacity = '1';
            }, 200);
        });
    });

    // Add keyboard navigation
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            const activeTab = document.querySelector('.filter-tab.active');
            const tabs = Array.from(filterTabs);
            const currentIndex = tabs.indexOf(activeTab);

            let nextIndex;
            if (e.key === 'ArrowLeft') {
                nextIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
            } else {
                nextIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
            }

            tabs[nextIndex].click();
            tabs[nextIndex].focus();
        }
    });

    // Search functionality
    const searchInput = createSearchInput();
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();

            alertCards.forEach(card => {
                const title = card.querySelector('.alert-header h4').textContent.toLowerCase();
                const message = card.querySelector('.alert-message').textContent.toLowerCase();
                const category = card.dataset.category.toLowerCase();

                const matches = title.includes(searchTerm) ||
                               message.includes(searchTerm) ||
                               category.includes(searchTerm);

                if (matches || searchTerm === '') {
                    card.style.display = 'flex';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

    // Priority sorting
    const sortButton = createSortButton();
    if (sortButton) {
        let sortOrder = 'desc'; // desc = high to low, asc = low to high

        sortButton.addEventListener('click', function() {
            const alertsList = document.querySelector('.alerts-list');
            const cards = Array.from(alertCards);

            const priorityOrder = { 'high': 3, 'medium': 2, 'low': 1 };

            cards.sort((a, b) => {
                const aSeverity = a.querySelector('.alert-severity').textContent.split(' ')[0];
                const bSeverity = b.querySelector('.alert-severity').textContent.split(' ')[0];

                const aValue = priorityOrder[aSeverity] || 0;
                const bValue = priorityOrder[bSeverity] || 0;

                return sortOrder === 'desc' ? bValue - aValue : aValue - bValue;
            });

            // Re-append sorted cards
            cards.forEach(card => alertsList.appendChild(card));

            // Toggle sort order
            sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';

            // Update button text
            this.innerHTML = `<i class="fas fa-sort"></i> Priority ${sortOrder === 'desc' ? '↓' : '↑'}`;
        });
    }
});

// Create search input
function createSearchInput() {
    const filterTabs = document.querySelector('.filter-tabs');
    if (!filterTabs) return null;

    const searchContainer = document.createElement('div');
    searchContainer.style.cssText = `
        margin-left: auto;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    `;

    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search alerts...';
    searchInput.style.cssText = `
        padding: 0.5rem 1rem;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        font-size: 0.875rem;
        width: 200px;
        transition: all 0.3s ease;
    `;

    searchInput.addEventListener('focus', function() {
        this.style.borderColor = '#16a34a';
        this.style.boxShadow = '0 0 0 3px rgba(22, 163, 74, 0.1)';
    });

    searchInput.addEventListener('blur', function() {
        this.style.borderColor = '#d1d5db';
        this.style.boxShadow = 'none';
    });

    const searchIcon = document.createElement('i');
    searchIcon.className = 'fas fa-search';
    searchIcon.style.color = '#6b7280';

    searchContainer.appendChild(searchIcon);
    searchContainer.appendChild(searchInput);
    filterTabs.appendChild(searchContainer);

    return searchInput;
}

// Create sort button
function createSortButton() {
    const alertsList = document.querySelector('.alerts-list');
    if (!alertsList) return null;

    const sortButton = document.createElement('button');
    sortButton.innerHTML = '<i class="fas fa-sort"></i> Priority ↓';
    sortButton.style.cssText = `
        margin-bottom: 1rem;
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid #d1d5db;
        border-radius: 8px;
        cursor: pointer;
        font-size: 0.875rem;
        color: #374151;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    `;

    sortButton.addEventListener('mouseenter', function() {
        this.style.background = 'rgba(255, 255, 255, 1)';
        this.style.borderColor = '#16a34a';
    });

    sortButton.addEventListener('mouseleave', function() {
        this.style.background = 'rgba(255, 255, 255, 0.9)';
        this.style.borderColor = '#d1d5db';
    });

    alertsList.parentNode.insertBefore(sortButton, alertsList);

    return sortButton;
}

// Update alert timestamps (for auto-refresh)
function updateAlertTimestamps() {
    const timeElements = document.querySelectorAll('.alert-time');

    timeElements.forEach(element => {
        // In a real application, you would calculate relative time
        // For demo purposes, we'll just add a visual indicator
        const icon = element.querySelector('i');
        if (icon) {
            icon.style.color = '#16a34a';
            setTimeout(() => {
                icon.style.color = '#6b7280';
            }, 1000);
        }
    });
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .alert-card.read {
        background: rgba(249, 250, 251, 0.8) !important;
    }

    .alert-card:hover {
        cursor: pointer;
    }

    .filter-tab:focus {
        outline: 2px solid #16a34a;
        outline-offset: 2px;
    }
`;
document.head.appendChild(style);

// Export functions for external use
window.AlertsManager = {
    filterAlerts: function(category) {
        const tab = document.querySelector(`[data-filter="${category}"]`);
        if (tab) tab.click();
    },

    searchAlerts: function(term) {
        const searchInput = document.querySelector('input[placeholder="Search alerts..."]');
        if (searchInput) {
            searchInput.value = term;
            searchInput.dispatchEvent(new Event('input'));
        }
    },

    markAllAsRead: function() {
        document.querySelectorAll('.alert-card').forEach(card => {
            card.classList.add('read');
            card.style.opacity = '0.7';
        });
    }
};