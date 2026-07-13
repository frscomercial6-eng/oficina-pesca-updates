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
            val trialAtivo = json.optBoolean("trial_ativo", false)
            val licencaAtiva = json.optBoolean("licenca_ativa", false)
            if (bloqueada || !ativa) {
                "$base/web/licenca-bloqueada"
            } else if (trialAtivo && !licencaAtiva) {
                trialPlansHtml(base)
            } else {
                BuildConfig.WEB_APP_URL
            }
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

        private fun trialPlansHtml(baseUrl: String): String {
                val html = """
                        <!DOCTYPE html>
                        <html lang='pt-BR'>
                        <head>
                            <meta charset='UTF-8'>
                            <meta name='viewport' content='width=device-width, initial-scale=1.0'>
                            <title>Planos Oficina de Pesca</title>
                            <style>
                                body { background:#181a1b; color:#f5f5f5; font-family:Segoe UI, Arial, sans-serif; margin:0; padding:24px; }
                                .wrap { max-width:1080px; margin:0 auto; }
                                h1 { color:#f5f5f5; margin:0 0 10px 0; font-size:32px; }
                                .sub { color:#ff9f43; margin-bottom:20px; font-weight:600; }
                                .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
                                .card { background:#202325; border:1px solid #3b3b3b; border-radius:18px; padding:18px; box-shadow:0 8px 24px rgba(0,0,0,.24); }
                                .promo { border:2px solid #00E676; }
                                .best { border:3px solid #FF9F43; }
                                .name { font-size:18px; font-weight:700; margin-bottom:10px; }
                                .price { font-size:24px; font-weight:800; margin-bottom:8px; }
                                .desc { color:#d5dbe1; min-height:54px; }
                                .cta { display:inline-block; margin-top:14px; text-decoration:none; background:#2196f3; color:#fff; padding:12px 16px; border-radius:12px; font-weight:700; }
                                .cta.best { background:#FF9F43; color:#000; }
                                .footer { margin-top:22px; color:#9fb0bf; font-size:14px; }
                            </style>
                        </head>
                        <body>
                            <div class='wrap'>
                                <h1>Escolha o melhor plano para sua oficina</h1>
                                <div class='sub'>Seu acesso atual está em Trial. A navegação completa será liberada após ativação.</div>
                                <div class='grid'>
                                    ${if (BuildConfig.PROMO_ATIVA) "<div class='card promo'><div class='name'>PROMOCIONAL</div><div class='price'>R$ ${BuildConfig.PROMO_VALOR}</div><div class='desc'>${BuildConfig.PROMO_NOME}</div><a class='cta' href='${BuildConfig.PLANO_LINK_PROMO}'>Assinar agora</a></div>" else ""}
                                    <div class='card'><div class='name'>MENSAL</div><div class='price'>R$ 69,90</div><div class='desc'>Acesso imediato ao sistema.</div><a class='cta' href='${BuildConfig.PLANO_LINK_MENSAL}'>Assinar agora</a></div>
                                    <div class='card'><div class='name'>TRIMESTRAL</div><div class='price'>R$ 179,90</div><div class='desc'>Ideal para começar.</div><a class='cta' href='${BuildConfig.PLANO_LINK_TRIMESTRAL}'>Assinar agora</a></div>
                                    <div class='card best'><div class='name'>SEMESTRAL</div><div class='price'>R$ 359,90</div><div class='desc'>Melhor escolha para economia.</div><a class='cta best' href='${BuildConfig.PLANO_LINK_SEMESTRAL}'>Assinar agora</a></div>
                                    <div class='card'><div class='name'>ANUAL</div><div class='price'>R$ 799,90</div><div class='desc'>Plano profissional de 12 meses.</div><a class='cta' href='${BuildConfig.PLANO_LINK_ANUAL}'>Assinar agora</a></div>
                                </div>
                                <div class='footer'>Aguardando confirmação automática do pagamento. Assim que a licença for ativada, o sistema completo será liberado.</div>
                            </div>
                            <script>
                                async function verificarLiberacao() {
                                    try {
                                        const resp = await fetch('${baseUrl}/api/licenca-status', { cache: 'no-store' });
                                        const data = await resp.json();
                                        const trial = Boolean(data && data.trial_ativo);
                                        const ativa = Boolean(data && (data.licenca_ativa || data.ativa));
                                        if (ativa && !trial) {
                                            window.location.replace('${BuildConfig.WEB_APP_URL}');
                                        }
                                    } catch (_) {}
                                }
                                setInterval(verificarLiberacao, 8000);
                            </script>
                        </body>
                        </html>
                """.trimIndent()

                return "data:text/html," + java.net.URLEncoder.encode(html, Charsets.UTF_8.name())
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
