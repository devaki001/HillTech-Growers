// Chart.js configuration and initialization
document.addEventListener('DOMContentLoaded', function() {
    // Chart.js default configuration
    Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    Chart.defaults.color = '#6b7280';
    Chart.defaults.plugins.legend.position = 'bottom';
    Chart.defaults.plugins.legend.labels.padding = 20;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;

    // Soil Moisture vs Time Chart
    const soilMoistureCtx = document.getElementById('soilMoistureChart');
    if (soilMoistureCtx && typeof soilMoistureData !== 'undefined') {
        new Chart(soilMoistureCtx, {
            type: 'line',
            data: {
                labels: soilMoistureData.map(d => d.time),
                datasets: [
                    {
                        label: 'Soil Moisture (%)',
                        data: soilMoistureData.map(d => d.moisture),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#3b82f6',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 6,
                        pointHoverRadius: 8
                    },
                    {
                        label: 'Optimal Range',
                        data: soilMoistureData.map(d => d.optimal_max),
                        borderColor: 'rgba(34, 197, 94, 0.3)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        borderWidth: 1,
                        fill: '+1',
                        tension: 0,
                        pointRadius: 0,
                        pointHoverRadius: 0
                    },
                    {
                        label: 'Optimal Min',
                        data: soilMoistureData.map(d => d.optimal_min),
                        borderColor: 'rgba(34, 197, 94, 0.3)',
                        backgroundColor: 'rgba(255, 255, 255, 1)',
                        borderWidth: 1,
                        fill: false,
                        tension: 0,
                        pointRadius: 0,
                        pointHoverRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            filter: function(legendItem, chartData) {
                                return legendItem.text !== 'Optimal Min';
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        titleColor: '#1f2937',
                        bodyColor: '#6b7280',
                        borderColor: '#e5e7eb',
                        borderWidth: 1,
                        cornerRadius: 8,
                        displayColors: true
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Time of Day'
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Moisture Level (%)'
                        },
                        min: 0,
                        max: 100
                    }
                }
            }
        });
    }

    // Rainfall vs Irrigation Demand Chart
    const rainfallIrrigationCtx = document.getElementById('rainfallIrrigationChart');
    if (rainfallIrrigationCtx && typeof rainfallIrrigationData !== 'undefined') {
        new Chart(rainfallIrrigationCtx, {
            type: 'bar',
            data: {
                labels: rainfallIrrigationData.map(d => d.day),
                datasets: [
                    {
                        label: 'Rainfall (mm)',
                        data: rainfallIrrigationData.map(d => d.rainfall),
                        backgroundColor: 'rgba(6, 182, 212, 0.8)',
                        borderColor: '#06b6d4',
                        borderWidth: 1,
                        borderRadius: 4,
                        borderSkipped: false
                    },
                    {
                        label: 'Irrigation Demand (L/m²)',
                        data: rainfallIrrigationData.map(d => d.irrigation_demand),
                        type: 'line',
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        borderWidth: 3,
                        fill: false,
                        tension: 0.4,
                        pointBackgroundColor: '#f97316',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Actual Irrigation (L/m²)',
                        data: rainfallIrrigationData.map(d => d.actual_irrigation),
                        type: 'line',
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        tension: 0.4,
                        pointBackgroundColor: '#22c55e',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    tooltip: {
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        titleColor: '#1f2937',
                        bodyColor: '#6b7280',
                        borderColor: '#e5e7eb',
                        borderWidth: 1,
                        cornerRadius: 8,
                        displayColors: true
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Day of Week'
                        }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Rainfall (mm)'
                        },
                        min: 0
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Irrigation (L/m²)'
                        },
                        grid: {
                            drawOnChartArea: false
                        },
                        min: 0
                    }
                }
            }
        });
    }

    // Crop Water Requirement vs Actual Irrigation Chart
    const cropWaterCtx = document.getElementById('cropWaterChart');
    if (cropWaterCtx && typeof cropWaterData !== 'undefined') {
        new Chart(cropWaterCtx, {
            type: 'bar',
            data: {
                labels: cropWaterData.map(d => d.crop),
                datasets: [
                    {
                        label: 'Water Requirement (L/m²)',
                        data: cropWaterData.map(d => d.requirement),
                        backgroundColor: 'rgba(245, 158, 11, 0.8)',
                        borderColor: '#f59e0b',
                        borderWidth: 1,
                        borderRadius: 4,
                        borderSkipped: false
                    },
                    {
                        label: 'Actual Applied (L/m²)',
                        data: cropWaterData.map(d => d.applied),
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                        borderRadius: 4,
                        borderSkipped: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    tooltip: {
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        titleColor: '#1f2937',
                        bodyColor: '#6b7280',
                        borderColor: '#e5e7eb',
                        borderWidth: 1,
                        cornerRadius: 8,
                        displayColors: true,
                        callbacks: {
                            afterBody: function(context) {
                                const dataIndex = context[0].dataIndex;
                                const efficiency = cropWaterData[dataIndex].efficiency;
                                return `Efficiency: ${efficiency}%`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Crop Types (Hilly Region Specialties)'
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(229, 231, 235, 0.5)'
                        },
                        title: {
                            display: true,
                            text: 'Water Volume (L/m²)'
                        },
                        min: 0
                    }
                }
            }
        });
    }
});

// Utility function to update charts with new data
function updateChartData(chart, newData) {
    chart.data.datasets.forEach((dataset, index) => {
        dataset.data = newData[index];
    });
    chart.update('active');
}

// Function to export chart as image
function exportChart(chartId, filename) {
    const chart = Chart.getChart(chartId);
    if (chart) {
        const url = chart.toBase64Image();
        const link = document.createElement('a');
        link.download = filename || 'chart.png';
        link.href = url;
        link.click();
    }
}

// Add export functionality to charts
document.addEventListener('DOMContentLoaded', function() {
    const chartContainers = document.querySelectorAll('.graph-card');

    chartContainers.forEach(container => {
        const canvas = container.querySelector('canvas');
        if (canvas) {
            const exportBtn = document.createElement('button');
            exportBtn.innerHTML = '<i class="fas fa-download"></i>';
            exportBtn.className = 'export-btn';
            exportBtn.style.cssText = `
                position: absolute;
                top: 10px;
                right: 10px;
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                padding: 8px;
                cursor: pointer;
                color: #6b7280;
                transition: all 0.3s ease;
            `;

            exportBtn.addEventListener('click', () => {
                exportChart(canvas.id, `${canvas.id}_export.png`);
            });

            exportBtn.addEventListener('mouseenter', () => {
                exportBtn.style.background = 'rgba(255, 255, 255, 1)';
                exportBtn.style.color = '#374151';
            });

            exportBtn.addEventListener('mouseleave', () => {
                exportBtn.style.background = 'rgba(255, 255, 255, 0.9)';
                exportBtn.style.color = '#6b7280';
            });

            container.style.position = 'relative';
            container.appendChild(exportBtn);
        }
    });
});