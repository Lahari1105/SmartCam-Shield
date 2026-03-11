// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-app.js";
import { getAnalytics } from "https://www.gstatic.com/firebasejs/12.10.0/firebase-analytics.js";
  // TODO: Add SDKs for Firebase products that you want to use
  // https://firebase.google.com/docs/web/setup#available-libraries

  // Your web app's Firebase configuration
  // For Firebase JS SDK v7.20.0 and later, measurementId is optional
  const firebaseConfig = {
    apiKey: "AIzaSyBRSTrTq_sBJ18EE_iLUj7m2eeFFN6KyIo",
    authDomain: "smartcam-shield.firebaseapp.com",
    projectId: "smartcam-shield",
    storageBucket: "smartcam-shield.firebasestorage.app",
    messagingSenderId: "171190774677",
    appId: "1:171190774677:web:edd3d8fdf92f018807649c",
    measurementId: "G-ZXM0BHZ8NP"
  };

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);