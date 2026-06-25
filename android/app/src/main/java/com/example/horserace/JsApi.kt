package com.example.horserace

import android.content.Context
import android.webkit.JavascriptInterface
import android.webkit.WebView

class JsApi(private val context: Context, private val webView: WebView) {

    @JavascriptInterface
    fun requestFcmToken() {
        // In a full implementation, you would use FirebaseMessaging.getInstance().token
        // and then call window.onFcmToken(token) back to the WebView via:
        // webView.post { webView.evaluateJavascript("window.onFcmToken('...')", null) }
    }
}
