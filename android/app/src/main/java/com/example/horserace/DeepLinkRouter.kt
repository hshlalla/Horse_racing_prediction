package com.example.horserace

import android.content.Intent
import android.net.Uri
import android.webkit.WebView

object DeepLinkRouter {
    /**
     * Inspects the intent to see if it contains a deep link (e.g. from an FCM notification).
     * If so, routes the WebView to the correct URL.
     */
    fun handleIntent(intent: Intent?, webView: WebView, baseUrl: String) {
        val action = intent?.action
        val data: Uri? = intent?.data

        if (Intent.ACTION_VIEW == action && data != null) {
            // Example: horserace://race/12345
            // Translates to: https://host/races/date/12345 (need date context or ID-based routing)
            // For simplicity, we just pass the path to the web view
            val path = data.path ?: ""
            webView.loadUrl("$baseUrl$path")
        }
    }
}
