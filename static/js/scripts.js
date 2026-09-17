// --- BEGIN: Firebase Setup ---
const firebaseConfig = {
  apiKey: "AIzaSyBzK6Gh3KQDGThfTsBVmSYRweSpOiz3BJM",
  authDomain: "moneypathai.firebaseapp.com",
  projectId: "moneypathai",
  storageBucket: "moneypathai.firebasestorage.app",
  messagingSenderId: "297607633480",
  appId: "1:297607633480:web:7b70174ce6119fe4af167d",
  measurementId: "G-YRGH2W9JY9"
};
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
window.firebaseAuthInstance = auth;
// --- END: Firebase Setup ---

document.addEventListener("DOMContentLoaded", function () {
  // Detect language from ?lang param (default 'en')
  function getLang() {
    const params = new URLSearchParams(window.location.search);
    return params.get('lang') === 'hi' ? 'hi' : 'en';
  }
  const lang = getLang();

  // Message dictionary
  const MESSAGES = {
    invalidPhone: {
      en: "Please enter a valid 10-digit phone number",
      hi: "कृपया वैध 10-अंकीय फ़ोन नंबर दर्ज करें"
    },
    otpSent: {
      en: phone => "OTP sent to " + phone,
      hi: phone => "OTP " + phone + " पर भेजा गया"
    },
    otpError: {
      en: msg => "Error sending OTP: " + msg,
      hi: msg => "OTP भेजने में त्रुटि: " + msg
    },
    enterOtp: {
      en: "Please enter a 6-digit OTP",
      hi: "कृपया 6-अंकीय OTP दर्ज करें"
    },
    loginSuccess: {
      en: "Logged in successfully!",
      hi: "सफलतापूर्वक लॉगिन हुआ!"
    },
    tokenFail: {
      en: msg => "Token verification failed: " + msg,
      hi: msg => "टोकन सत्यापन विफल: " + msg
    },
    verifyError: {
      en: msg => "Error verifying token: " + msg,
      hi: msg => "टोकन सत्यापन में त्रुटि: " + msg
    },
    otpInvalid: {
      en: "Invalid OTP. Please try again.",
      hi: "OTP अमान्य है। कृपया पुनः प्रयास करें।"
    }
  };

  // Utility for toast notification
  window.showToast = window.showToast ?? function(message, type="info") {
    const toast = document.getElementById("notification-toast");
    toast.textContent = message;
    if (type === "success") {
      toast.className = "fixed top-8 right-8 z-50 px-6 py-4 rounded-lg bg-[#1793b8] text-white text-lg shadow-lg";
    } else if (type === "error") {
      toast.className = "fixed top-8 right-8 z-50 px-6 py-4 rounded-lg bg-red-600 text-white text-lg shadow-lg";
    } else {
      toast.className = "fixed top-8 right-8 z-50 px-6 py-4 rounded-lg bg-[#1793b8] text-white text-lg shadow-lg";
    }
    toast.style.display = "block";
    toast.style.opacity = 1;
    setTimeout(() => {
      toast.style.opacity = 0;
      setTimeout(() => {
        toast.style.display = "none";
      }, 300);
    }, 2500);
  };

  // Firebase phone auth logic
  const auth = window.firebaseAuthInstance || null;
  let confirmationResult = null;

  // Render reCAPTCHA
  if (auth) {
    window.recaptchaVerifier = new firebase.auth.RecaptchaVerifier('recaptcha-container', {
      'size': 'invisible',
      'callback': () => {}
    });
  }

  // Elements
  const phoneInput = document.getElementById("phone-number");
  const sendOtpBtn = document.getElementById("send-otp-btn");
  const otpInput = document.getElementById("otp-input");
  const verifyOtpBtn = document.getElementById("verify-otp-btn");
  const phoneSection = document.getElementById("phone-section");
  const otpSection = document.getElementById("otp-section");

  // Send OTP
  sendOtpBtn.addEventListener("click", () => {
    const phone = phoneInput.value;
    if (!phone.match(/^\d{10}$/)) {
      showToast(MESSAGES.invalidPhone[lang], "error");
      return;
    }
    const fullPhone = "+91" + phone;
    sendOtpBtn.disabled = true;

    const appVerifier = window.recaptchaVerifier;
    firebase.auth().signInWithPhoneNumber(fullPhone, appVerifier)
      .then((result) => {
        confirmationResult = result;
        showToast(MESSAGES.otpSent[lang](fullPhone), "success");
        phoneSection.style.display = "none";
        otpSection.style.display = "block";
      })
      .catch((error) => {
        showToast(MESSAGES.otpError[lang](error.message), "error");
        sendOtpBtn.disabled = false;
      });
  });

  // Verify OTP
  verifyOtpBtn.addEventListener("click", () => {
    const code = otpInput.value;
    if (code.length !== 6) {
      showToast(MESSAGES.enterOtp[lang], "error");
      return;
    }
    verifyOtpBtn.disabled = true;

    confirmationResult.confirm(code)
      .then(async (result) => {
        const user = result.user;
        const idToken = await user.getIdToken();

        // Send token to backend
        fetch('/verify-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ idToken })
        })
        .then(res => res.json())
        .then(data => {
          if (data.uid) {
            showToast(MESSAGES.loginSuccess[lang], 'success');
            setTimeout(() => {
              window.location.href = '/onboarding/user';
            }, 1200);
          } else {
            showToast(MESSAGES.tokenFail[lang](data.error), 'error');
            verifyOtpBtn.disabled = false;
          }
        })
        .catch(error => {
          showToast(MESSAGES.verifyError[lang](error), 'error');
          verifyOtpBtn.disabled = false;
        });
      })
      .catch((error) => {
        showToast(MESSAGES.otpInvalid[lang], "error");
        verifyOtpBtn.disabled = false;
      });
  });
});
