package com.oficinapesca.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SistemaPrincipalActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var webView: WebView

    private val urlsCandidatas: List<String>
        get() {
            val mobileUrl = BuildConfig.MOBILE_PUBLIC_URL.trim().trimEnd('/')
            val serverBase = BuildConfig.SERVER_BASE_URL.trim().trimEnd('/')

            val candidatos = mutableListOf<String>()
            if (mobileUrl.isNotEmpty()) {
                candidatos += mobileUrl
                candidatos += "$mobileUrl/web/login"
                candidatos += "$mobileUrl/app"
            }

            if (serverBase.isNotEmpty()) {
                candidatos += "$serverBase/web/login"
                candidatos += "$serverBase/app"
            }

            candidatos += "http://10.0.2.2:8000/web/login"
            candidatos += "http://10.0.2.2:8000/app"

            return candidatos.distinct()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montarInterface()
        configurarWebView()
        carregarPrimeiraUrlDisponivel()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configurarWebView() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.databaseEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.cacheMode = WebSettings.LOAD_DEFAULT
        webView.webChromeClient = WebChromeClient()
    }

    private fun montarInterface() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0E1524"))
        }

        statusView = TextView(this).apply {
            text = "Carregando interface principal..."
            setTextColor(Color.parseColor("#9CA3AF"))
            textSize = 13f
            setPadding(24, 18, 24, 10)
        }

        webView = WebView(this)

        root.addView(
            statusView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
        )
        root.addView(
            webView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f,
            )
        )

        setContentView(root)
    }

    private fun carregarPrimeiraUrlDisponivel() {
        val candidatos = urlsCandidatas
        if (candidatos.isEmpty()) {
            statusView.text = "URL principal não configurada para o app."
            return
        }

        tentarCarregar(candidatos, 0)
    }

    private fun tentarCarregar(candidatos: List<String>, index: Int) {
        if (index >= candidatos.size) {
            statusView.text = "Não foi possível conectar à interface principal. Verifique o servidor e a URL pública no config.cfg."
            return
        }

        val url = candidatos[index]
        statusView.text = "Conectando: $url"

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, loadedUrl: String?) {
                super.onPageFinished(view, loadedUrl)
                statusView.text = "Conectado: ${loadedUrl ?: url}"
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    tentarCarregar(candidatos, index + 1)
                }
            }
        }

        webView.loadUrl(url)
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
            return
        }
        super.onBackPressed()
    }
}
