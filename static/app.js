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

    // ============================================================
    // Garmin Connect Login / MFA / Logout
    // ============================================================
    (function initGarminAuth() {
        var section   = $('#garmin-auth-section');
        if (!section.length) return;

        var urls = {
            status: section.data('status-url'),
            login:  section.data('login-url'),
            mfa:    section.data('mfa-url'),
            logout: section.data('logout-url')
        };

        var $loading   = $('#garmin-status-loading');
        var $loggedIn  = $('#garmin-logged-in');
        var $loggedOut = $('#garmin-logged-out');
        var $loginForm = $('#garmin-login-form');
        var $mfaForm   = $('#garmin-mfa-form');
        var $msg       = $('#garmin-auth-message');
        var $name      = $('#garmin-display-name');

        function showMsg(text, type) {
            $msg.text(text)
                .removeClass('alert-success alert-error alert-info alert-warning')
                .addClass('alert-' + (type || 'info'))
                .show();
        }
        function hideMsg() { $msg.hide(); }

        function showLoggedIn(displayName) {
            $loading.hide(); $loggedOut.hide(); $mfaForm.hide();
            $name.text(displayName || 'Garmin User');
            $loggedIn.show();
        }
        function showLoggedOut() {
            $loading.hide(); $loggedIn.hide(); $mfaForm.hide();
            $loggedOut.show();
            $loginForm.show();
        }
        function showMfa() {
            $loading.hide(); $loggedIn.hide(); $loggedOut.hide(); $loginForm.hide();
            $mfaForm.show();
            $('#garmin-mfa-code').val('').focus();
        }

        function setButtonLoading($btn, loading) {
            if (loading) {
                $btn.data('orig-text', $btn.text());
                $btn.text('Please wait...').prop('disabled', true);
            } else {
                $btn.text($btn.data('orig-text') || $btn.text()).prop('disabled', false);
            }
        }

        // Check status on page load
        $.getJSON(urls.status, function(data) {
            if (data.logged_in) {
                showLoggedIn(data.display_name);
            } else {
                showLoggedOut();
            }
        }).fail(function() {
            showLoggedOut();
        });

        // Login button
        $('#garmin-login-btn').on('click', function() {
            var email    = $('#garmin-email').val().trim();
            var password = $('#garmin-password').val();
            if (!email || !password) {
                showMsg('Please enter both email and password.', 'warning');
                return;
            }
            hideMsg();
            var $btn = $(this);
            setButtonLoading($btn, true);

            $.ajax({
                url: urls.login,
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ email: email, password: password }),
                success: function(resp) {
                    setButtonLoading($btn, false);
                    if (resp.status === 'success') {
                        showMsg(resp.message, 'success');
                        showLoggedIn(resp.display_name);
                        // Clear password from form
                        $('#garmin-password').val('');
                    } else if (resp.status === 'needs_mfa') {
                        showMsg(resp.message, 'info');
                        showMfa();
                    } else {
                        showMsg(resp.message, 'error');
                    }
                },
                error: function(xhr) {
                    setButtonLoading($btn, false);
                    var resp = xhr.responseJSON || {};
                    showMsg(resp.message || 'Login request failed.', 'error');
                }
            });
        });

        // Allow Enter key in password field to submit
        $('#garmin-password').on('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); $('#garmin-login-btn').click(); }
        });

        // MFA verify button
        $('#garmin-mfa-btn').on('click', function() {
            var code = $('#garmin-mfa-code').val().trim();
            if (!code) {
                showMsg('Please enter the MFA code.', 'warning');
                return;
            }
            hideMsg();
            var $btn = $(this);
            setButtonLoading($btn, true);

            $.ajax({
                url: urls.mfa,
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ mfa_code: code }),
                success: function(resp) {
                    setButtonLoading($btn, false);
                    if (resp.status === 'success') {
                        showMsg(resp.message, 'success');
                        showLoggedIn(resp.display_name);
                        $('#garmin-password').val('');
                    } else {
                        showMsg(resp.message, 'error');
                        // Keep MFA form visible so user can retry
                        $('#garmin-mfa-code').val('').focus();
                    }
                },
                error: function(xhr) {
                    setButtonLoading($btn, false);
                    var resp = xhr.responseJSON || {};
                    showMsg(resp.message || 'MFA verification failed.', 'error');
                }
            });
        });

        // Allow Enter key in MFA field to submit
        $('#garmin-mfa-code').on('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); $('#garmin-mfa-btn').click(); }
        });

        // MFA cancel button
        $('#garmin-mfa-cancel-btn').on('click', function() {
            hideMsg();
            showLoggedOut();
        });

        // Logout button
        $('#garmin-logout-btn').on('click', function() {
            if (!confirm('Log out of Garmin Connect?')) return;
            hideMsg();
            var $btn = $(this);
            setButtonLoading($btn, true);

            $.ajax({
                url: urls.logout,
                method: 'POST',
                contentType: 'application/json',
                success: function(resp) {
                    setButtonLoading($btn, false);
                    showMsg(resp.message, 'success');
                    showLoggedOut();
                },
                error: function() {
                    setButtonLoading($btn, false);
                    showMsg('Logout request failed.', 'error');
                }
            });
        });
    })();

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
