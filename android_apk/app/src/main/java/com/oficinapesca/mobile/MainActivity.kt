package com.oficinapesca.mobile

import android.os.Bundle
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Dark Mode padrão no container.
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)

        webView = WebView(this)
        setContentView(webView)

        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.loadsImagesAutomatically = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

        webView.webChromeClient = WebChromeClient()
        webView.addJavascriptInterface(FirebaseBridge(), "OficinaFirebase")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                val json = FirebaseBridge().firebaseJson().replace("\\", "\\\\").replace("'", "\\'")
                view?.evaluateJavascript(
                    "window.__OFP_FIREBASE_CONFIG__ = JSON.parse('$json');window.dispatchEvent(new Event('ofp-firebase-config-ready'));",
                    null
                )
                super.onPageFinished(view, url)
            }
        }

        verificarLicencaECarregar()
    }

    private fun verificarLicencaECarregar() {
        Thread {
            val alvo = resolverDestinoInicial()
            runOnUiThread {
                webView.loadUrl(alvo)
            }
        }.start()
    }

    private fun resolverDestinoInicial(): String {
        return try {
            val base = baseUrl()
            val conn = URL("$base/api/licenca-status").openConnection() as HttpURLConnection
            conn.requestMethod = "GET"
            conn.connectTimeout = 4000
            conn.readTimeout = 4000
            conn.setRequestProperty("User-Agent", "OficinaPescaWebView/${BuildConfig.VERSION_NAME}")

            val body = conn.inputStream.bufferedReader().use { it.readText() }
            val json = JSONObject(body)
            val bloqueada = json.optBoolean("bloqueada", false)
            val ativa = json.optBoolean("ativa", true)
            if (bloqueada || !ativa) "$base/web/licenca-bloqueada" else BuildConfig.WEB_APP_URL
        } catch (exc: Exception) {
            Log.w("OficinaPesca", "Falha ao validar licença antes do load: ${exc.message}")
            localBlockedHtml()
        }
    }

    private fun baseUrl(): String {
        val url = BuildConfig.WEB_APP_URL.trim()
        val parsed = URL(url)
        val port = if (parsed.port > 0) ":${parsed.port}" else ""
        return "${parsed.protocol}://${parsed.host}$port"
    }

    private fun localBlockedHtml(): String {
        return "data:text/html," + java.net.URLEncoder.encode(
            """
            <!DOCTYPE html>
            <html lang='pt-BR'>
            <head>
              <meta charset='UTF-8'>
              <meta name='viewport' content='width=device-width, initial-scale=1.0'>
              <title>Licença Bloqueada</title>
              <style>
                body { background:#0f1923; color:#ecf0f1; display:flex; align-items:center; justify-content:center; min-height:100vh; font-family:Arial,sans-serif; margin:0; }
                .box { max-width:520px; background:#1a2535; border-radius:20px; padding:32px 24px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,.45); }
                h1 { color:#f39c12; margin-top:0; }
              </style>
            </head>
            <body>
              <div class='box'>
                <h1>Acesso Bloqueado</h1>
                <p>Não foi possível validar a licença deste sistema no servidor.</p>
                <p>Verifique a licença no Desktop ou a conectividade com a oficina.</p>
                <p>v${BuildConfig.VERSION_NAME}</p>
              </div>
            </body>
            </html>
            """.trimIndent(),
            Charsets.UTF_8.name()
        )
    }

    override fun onBackPressed() {
        if (this::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    inner class FirebaseBridge {
        @JavascriptInterface
        fun firebaseJson(): String {
            val payload = JSONObject()
            payload.put("apiKey", BuildConfig.FIREBASE_API_KEY)
            payload.put("authDomain", BuildConfig.FIREBASE_AUTH_DOMAIN)
            payload.put("databaseURL", BuildConfig.FIREBASE_DATABASE_URL)
            payload.put("projectId", BuildConfig.FIREBASE_PROJECT_ID)
            payload.put("storageBucket", BuildConfig.FIREBASE_STORAGE_BUCKET)
            payload.put("messagingSenderId", BuildConfig.FIREBASE_MESSAGING_SENDER_ID)
            payload.put("appId", BuildConfig.FIREBASE_APP_ID)
            payload.put("syncChannel", BuildConfig.FIREBASE_SYNC_CHANNEL)
            return payload.toString()
        }
    }
}
