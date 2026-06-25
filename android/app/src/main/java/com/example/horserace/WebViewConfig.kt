package com.example.horserace

import android.annotation.SuppressLint
import android.webkit.CookieManager
import android.webkit.WebSettings
import android.webkit.WebView

object WebViewConfig {
    @SuppressLint("SetJavaScriptEnabled")
    fun setupWebView(webView: WebView) {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        
        // Caching
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        // Security configuration based on design doc
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        settings.allowFileAccess = false
        settings.allowFileAccessFromFileURLs = false
        settings.allowUniversalAccessFromFileURLs = false

        // User-Agent Override
        settings.userAgentString = "HorseRaceAndroid/1.0"

        // Cookies
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(webView, true)
    }
}
