// ⚙️ API: same-domain na Vercel function na (/api/send-trial).
// Kung gusto mo ibalik sa Render, palitan ng full URL ng Render backend.
const BACKEND_URL = "";

(() => {
    const form = document.getElementById("trial-form");
    const emailInput = document.getElementById("email");
    const submitBtn = document.getElementById("submit-btn");
    const alertBox = document.getElementById("alert");

    const submitLabel = submitBtn.textContent;

    function showAlert(message, type) {
        alertBox.textContent = "";
        const icon = type === "success" ? "✅" : "❌";
        alertBox.textContent = `${icon} ${message}`;
        alertBox.className = `alert ${type}`;
    }

    function setLoading(isLoading) {
        submitBtn.disabled = isLoading;
        if (isLoading) {
            submitBtn.innerHTML =
                '<span class="spinner"></span> Sending...';
        } else {
            submitBtn.textContent = submitLabel;
        }
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const email = emailInput.value.trim();
        if (!email || !email.includes("@")) {
            showAlert("Please enter a valid email address.", "error");
            return;
        }

        setLoading(true);
        alertBox.className = "alert hidden";

        try {
            const res = await fetch(`${BACKEND_URL}/api/send-trial`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email }),
            });

            const data = await res.json();

            if (data.success) {
                showAlert(data.message, "success");
            } else {
                let msg = data.message;
                if (data.debug) {
                    msg += " — [debug] " + data.debug;
                }
                showAlert(msg, "error");
            }
        } catch (err) {
            showAlert("Could not reach the API. Make sure the Vercel deployment includes the /api function and is live.", "error");
        } finally {
            setLoading(false);
        }
    });
})();