package com.example.horserace

import android.util.Log

/**
 * FcmBridge stub.
 * In a real implementation, this class extends FirebaseMessagingService
 * and handles onNewToken and onMessageReceived.
 */
class FcmBridge {
    fun onNewToken(token: String) {
        Log.d("FcmBridge", "Refreshed token: $token")
        // Implementation would send this to MainActivity to inject into WebView via JsApi
    }

    fun onMessageReceived(remoteMessage: Any) {
        // Implementation would construct a notification that triggers DeepLinkRouter
        Log.d("FcmBridge", "Message received")
    }
}
