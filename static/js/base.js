document.addEventListener("DOMContentLoaded", function() {
    const banner = document.getElementById("banner");
    const closeButton = document.getElementById("close-banner");

    if (banner && closeButton) {
        if (localStorage.getItem('bannerDismissed')) {
            banner.style.display = 'none';
        }

        closeButton.addEventListener("click", function() {
            banner.style.display = 'none';
            localStorage.setItem('bannerDismissed', 'true');
        });
    }
});
