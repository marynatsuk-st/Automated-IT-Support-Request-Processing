document.addEventListener("DOMContentLoaded", function() {
    
    // Select the necessary elements
    const nav = document.querySelector("nav");
    const sidebarToggle = document.querySelector(".sidebar-toggle");

    // Check if the elements exist on the page
    if (nav && sidebarToggle) {
        
        // --- Sidebar Toggle Event ---
        sidebarToggle.addEventListener("click", () => {
            nav.classList.toggle("close");

            // --- Save sidebar state to localStorage ---
            if (nav.classList.contains("close")) {
                localStorage.setItem("sidebarStatus", "close");
            } else {
                localStorage.setItem("sidebarStatus", "open");
            }
        });

        // --- Check saved state on page load ---
        let getStatus = localStorage.getItem("sidebarStatus");
        if (getStatus === "close") {
            nav.classList.add("close");
        }
    }
});