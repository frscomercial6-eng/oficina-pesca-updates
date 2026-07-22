package com.oficinapesca.mobile

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.net.http.SslError
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.SslErrorHandler
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SistemaPrincipalActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var webView: WebView
    private lateinit var botaoTentar: Button

    private val mainHandler = Handler(Looper.getMainLooper())
    private var indiceAtual = 0
    private var carregamentoConcluido = false
    private var timeoutAtivo: Runnable? = null

    companion object {
        private const val LOAD_TIMEOUT_MS = 9000L
    }

    private val urlsCandidatas: List<String>
        get() {
            val publicUrl = BuildConfig.MOBILE_PUBLIC_URL.trim().trimEnd('/')
            if (publicUrl.isBlank()) {
                return emptyList()
            }

            val candidatos = mutableListOf<String>()
            candidatos += publicUrl

            if (!publicUrl.endsWith("/app", ignoreCase = true)) {
                candidatos += "$publicUrl/app"
            }

            if (!publicUrl.endsWith("/web/login", ignoreCase = true)) {
                candidatos += "$publicUrl/web/login"
            }

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
            cacheMode = WebSettings.LOAD_DEFAULT
            setSupportMultipleWindows(false)
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.JELLY_BEAN) {
                allowFileAccessFromFileURLs = true
                allowUniversalAccessFromFileURLs = true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                super.onProgressChanged(view, newProgress)
                if (!carregamentoConcluido) {
                    statusView.text = "Conectando... $newProgress%"
                }
            }
        }
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

        botaoTentar = Button(this).apply {
            text = "Tentar novamente"
            isAllCaps = false
            visibility = Button.GONE
            setOnClickListener {
                visibility = Button.GONE
                carregarPrimeiraUrlDisponivel()
            }
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
            botaoTentar,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
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
        indiceAtual = 0
        carregamentoConcluido = false
        cancelarTimeout()
        if (candidatos.isEmpty()) {
            statusView.text = "URL pública do sistema não configurada. Defina OFP_WEB_APP_URL ou url_app_celular_publica."
            botaoTentar.visibility = Button.VISIBLE
            return
        }

        tentarCarregar(candidatos, 0)
    }

    private fun tentarCarregar(candidatos: List<String>, index: Int) {
        cancelarTimeout()
        if (index >= candidatos.size) {
            exibirTelaFalhaAmigavel()
            return
        }

        indiceAtual = index
        val url = candidatos[index]
        carregamentoConcluido = false
        statusView.text = "Conectando: $url"
        botaoTentar.visibility = Button.GONE

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false
            }

            override fun onPageStarted(view: WebView?, loadingUrl: String?, favicon: Bitmap?) {
                super.onPageStarted(view, loadingUrl, favicon)
                agendarTimeout(candidatos, index)
            }

            override fun onPageFinished(view: WebView?, loadedUrl: String?) {
                super.onPageFinished(view, loadedUrl)
                cancelarTimeout()
                carregamentoConcluido = true
                statusView.text = "Conectado: ${loadedUrl ?: url}"
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?,
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (request?.isForMainFrame == true) {
                    tentarProximaUrl(candidatos, index, "Erro HTTP ${errorResponse?.statusCode ?: 0}")
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
                    tentarProximaUrl(candidatos, index, if (descricao.isNotBlank()) descricao else "Falha de rede")
                }
            }

            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                handler?.proceed()
            }
        }

        webView.loadUrl(url)
    }

    private fun tentarProximaUrl(candidatos: List<String>, index: Int, motivo: String) {
        if (index != indiceAtual || carregamentoConcluido) {
            return
        }
        cancelarTimeout()
        statusView.text = "Falha em ${candidatos[index]} ($motivo). Tentando próxima rota..."
        mainHandler.post { tentarCarregar(candidatos, index + 1) }
    }

    private fun agendarTimeout(candidatos: List<String>, index: Int) {
        cancelarTimeout()
        timeoutAtivo = Runnable {
            if (!carregamentoConcluido && index == indiceAtual) {
                tentarProximaUrl(candidatos, index, "timeout")
            }
        }
        mainHandler.postDelayed(timeoutAtivo!!, LOAD_TIMEOUT_MS)
    }

    private fun cancelarTimeout() {
        timeoutAtivo?.let { mainHandler.removeCallbacks(it) }
        timeoutAtivo = null
    }

    private fun exibirTelaFalhaAmigavel() {
        cancelarTimeout()
        botaoTentar.visibility = Button.VISIBLE
        statusView.text = "Não foi possível conectar ao servidor do sistema."
        webView.loadDataWithBaseURL(
            null,
            """
            <html><body style=\"background:#0E1524;color:#E5E7EB;font-family:sans-serif;padding:22px;\">
            <h3 style=\"color:#FCD34D;\">Servidor indisponível</h3>
            <p>Não conseguimos abrir a interface web do sistema neste dispositivo.</p>
            <p>Confirme se a URL pública do app celular está configurada e acessível pela internet móvel.</p>
            <p>Tente novamente em alguns segundos.</p>
            </body></html>
            """.trimIndent(),
            "text/html",
            "UTF-8",
            null,
        )
    }

    override fun onDestroy() {
        cancelarTimeout()
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
