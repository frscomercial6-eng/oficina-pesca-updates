package com.oficinapesca.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.http.SslError
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.SslErrorHandler
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject

class SistemaPrincipalActivity : AppCompatActivity() {
    private lateinit var webView: WebView

    private val mainHandler = Handler(Looper.getMainLooper())
    private var statusMonitorAtivo = false
    private var ultimaAssinaturaStatus = ""

    private val statusMonitor = object : Runnable {
        override fun run() {
            if (!statusMonitorAtivo) {
                return
            }
            sincronizarStatusStartupComWebView()
            mainHandler.postDelayed(this, 250L)
        }
    }

    companion object {
        private const val TAG = "OficinaPesca"
        private const val PAINEL_URL_ABSOLUTA = "https://oficinapescasystem.web.app/app"
    }

    private val urlPainel: String
        get() {
            val buildConfigUrl = BuildConfig.MOBILE_PUBLIC_URL.trim().trimEnd('/')
            return if (buildConfigUrl.isNotBlank()) {
                buildConfigUrl
            } else {
                PAINEL_URL_ABSOLUTA
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(TAG, "SistemaPrincipalActivity iniciada em modo container WebView limpo.")
        Log.i(TAG, "URL absoluta do painel: $urlPainel")
        montarInterface()
        configurarWebView()
        limparEstadoWebView()
        iniciarMonitorStatusStartup()
        carregarPainelPrincipal()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configurarWebView() {
        webView.setBackgroundColor(Color.parseColor("#0E1524"))
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            javaScriptCanOpenWindowsAutomatically = true
            loadsImagesAutomatically = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_NO_CACHE
            setSupportMultipleWindows(false)
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.JELLY_BEAN) {
                allowFileAccessFromFileURLs = true
                allowUniversalAccessFromFileURLs = true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                if (consoleMessage != null) {
                    Log.d(
                        TAG,
                        "WebView console [${consoleMessage.messageLevel()}] " +
                            "${consoleMessage.sourceId()}:${consoleMessage.lineNumber()} -> ${consoleMessage.message()}"
                    )
                }
                return super.onConsoleMessage(consoleMessage)
            }
        }
    }

    private fun limparEstadoWebView() {
        try {
            val cookieManager = CookieManager.getInstance()
            cookieManager.removeAllCookies(null)
            cookieManager.flush()
        } catch (exc: Exception) {
            Log.w(TAG, "Falha ao limpar cookies da WebView: ${exc.message}")
        }
        webView.clearHistory()
        webView.clearCache(true)
        webView.clearFormData()
    }

    private fun montarInterface() {
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.parseColor("#0E1524"))
        }

        webView = WebView(this)

        root.addView(
            webView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            )
        )

        setContentView(root)
    }

    private fun carregarPainelPrincipal() {
        val url = urlPainel
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, loadedUrl: String?) {
                super.onPageFinished(view, loadedUrl)
                val finalUrl = loadedUrl ?: url
                sincronizarStatusStartupComWebView()
                Log.i(TAG, "onPageFinished: $finalUrl")
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?,
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    Log.w(
                        TAG,
                        "Erro HTTP main frame em ${request.url}: status=${errorResponse?.statusCode ?: 0}"
                    )
                    exibirFalhaCarregamento(url)
                }
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    val descricao = error?.description?.toString()?.trim().orEmpty()
                    val codigo = error?.errorCode ?: 0
                    Log.w(
                        TAG,
                        "Erro de rede main frame em ${request.url}: code=$codigo, desc='${if (descricao.isNotBlank()) descricao else "sem_descricao"}'"
                    )
                    exibirFalhaCarregamento(url)
                }
            }

            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                Log.w(TAG, "SSL error recebido para ${error?.url}. Prosseguindo por política atual.")
                handler?.proceed()
            }
        }

        Log.i(TAG, "Carregando painel absoluto: $url")
        webView.loadUrl(url)
    }

    private fun exibirFalhaCarregamento(url: String) {
        Log.e(TAG, "Falha ao carregar painel absoluto: $url")
        webView.loadDataWithBaseURL(
            null,
            """
            <html><body style="background:#0E1524;color:#E5E7EB;font-family:sans-serif;padding:22px;">
            <h3 style="color:#FCD34D;">Falha de conexão</h3>
            <p>Não foi possível carregar o painel interno da aplicação.</p>
            <p>Toque em "Recarregar" para tentar novamente.</p>
            <button style="margin-top:12px;padding:10px 14px;border-radius:8px;border:0;background:#22C55E;color:#0B1220;font-weight:700;"
                onclick="location.href='${url}';">Recarregar</button>
            </body></html>
            """.trimIndent(),
            "text/html",
            "UTF-8",
            null,
        )
    }

    private fun iniciarMonitorStatusStartup() {
        if (statusMonitorAtivo) {
            return
        }
        statusMonitorAtivo = true
        mainHandler.post(statusMonitor)
    }

    private fun pararMonitorStatusStartup() {
        statusMonitorAtivo = false
        mainHandler.removeCallbacks(statusMonitor)
    }

    private fun sincronizarStatusStartupComWebView() {
        if (!::webView.isInitialized) {
            return
        }

        val snapshot = StartupConnectionState.current()
        val assinatura = "${snapshot.state}|${snapshot.message}|${snapshot.dotColor}"
        if (assinatura == ultimaAssinaturaStatus) {
            return
        }
        ultimaAssinaturaStatus = assinatura

        val texto = if (snapshot.state == "error") "Erro de Conexão" else "Conectado"
        val payload = JSONObject()
            .put("state", snapshot.state)
            .put("text", texto)
            .put("dotColor", snapshot.dotColor)
            .toString()

        webView.post {
            webView.evaluateJavascript("window.ofpApplyConnectionStatus($payload);", null)
        }
    }

    override fun onDestroy() {
        pararMonitorStatusStartup()
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
            return
        }
        super.onBackPressed()
    }
}