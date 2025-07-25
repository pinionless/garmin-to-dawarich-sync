$(document).ready(function() {
    let pollingInterval;
    const statusContainer = $('#custom-check-status-container');
    const statusUrl = statusContainer.data('status-url');
    const startBtn = $('#start-custom-check-btn, #mobile-start-custom-check-btn');
    const stopBtn = $('#stop-custom-check-btn, #mobile-stop-custom-check-btn');
    const settingsPanel = $('.container.settings');
    const settingsBtn = $('#mobile-settings-btn');
    const overlay = $('.overlay');

    if (!statusUrl) {
        return;
    }

    function checkStatus() {
        $.getJSON(statusUrl, function(data) {
            const statusDiv = $('#custom-check-status');

            if (data.is_running) {
                statusDiv.text('Background Task: ' + data.message);
                statusContainer.show();
                startBtn.removeClass('btn-primary').addClass('btn-secondary');
                stopBtn.removeClass('btn-secondary').addClass('btn-primary');
            } else {
                // If it was running and now it's not, show the final message and then stop polling.
                if (pollingInterval) {
                    statusDiv.text('Background Task: ' + data.message);
                    statusContainer.show();
                    // Hide the message after a few seconds
                    setTimeout(function() {
                        statusContainer.hide();
                    }, 5000);
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    startBtn.removeClass('btn-secondary').addClass('btn-primary');
                    stopBtn.removeClass('btn-primary').addClass('btn-secondary');
                }
            }
        });
    }

    // We need a way to know when to start polling.
    // A simple way is to check once on page load. If it's running, start the interval.
    // The /start_custom_check route redirects back, so the page will reload and polling will start.
    $.getJSON(statusUrl, function(data) {
        if (data.is_running) {
            if (!pollingInterval) {
                checkStatus(); // Initial check
                pollingInterval = setInterval(checkStatus, 2000); // Poll every 2 seconds
            }
        }
    });

    $('.mobile-header .btn').on('click', function(e) {
        if ($(this).hasClass('no-confirm')) {
            return;
        }
        const title = $(this).attr('title');
        if (!confirm('Are you sure you want to ' + title + '?')) {
            e.preventDefault();
        }
    });

    function toggleSettings(e) {
        if (e) e.preventDefault();
        settingsPanel.toggleClass('open');
        overlay.toggleClass('open');
        settingsBtn.toggleClass('active');
    }

    settingsBtn.on('click', toggleSettings);
    overlay.on('click', toggleSettings);

    // Action Modal Logic
    $('.open-action-modal').on('click', function(e) {
        e.preventDefault();
        const modalId = $(this).data('modal-id');
        $('#' + modalId).addClass('open');
    });

    // Close modal when clicking the close button
    $('.action-modal .close-modal').on('click', function() {
        $(this).closest('.action-modal').removeClass('open');
    });

    // Close modal when clicking on the backdrop
    $('.action-modal').on('click', function(e) {
        if ($(e.target).is('.action-modal')) {
            $(this).removeClass('open');
        }
    });
});
