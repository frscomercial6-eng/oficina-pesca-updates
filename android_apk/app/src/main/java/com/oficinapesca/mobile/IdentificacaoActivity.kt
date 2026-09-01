package com.oficinapesca.mobile

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.util.Log
import android.util.Patterns
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale

/**
 * Tela de identificação exibida na primeira abertura do APK: pede o e-mail
 * cadastrado da Oficina e valida a assinatura/licença ativa contra a API do
 * Render antes de liberar a tela principal (WebView).
 */
class IdentificacaoActivity : AppCompatActivity() {

    private data class ResultadoLicenca(
        val payload: JSONObject?,
        val diagnostico: String = "",
    )

    companion object {
        private const val TAG = "OficinaPesca"
        const val PREFS_NAME = "ofp_licenca_prefs"
        const val KEY_EMAIL_VALIDADO = "email_validado"
        const val EXTRA_EMAIL_DESKTOP = "email_desktop"
    }

    private lateinit var campoEmail: EditText
    private lateinit var botaoEntrar: Button
    private lateinit var botaoPlanos: Button
    private lateinit var textoPlanos: TextView
    private lateinit var textoMensagem: TextView
    private lateinit var progresso: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        montarInterface()

        val emailDoDesktop = intent.getStringExtra(EXTRA_EMAIL_DESKTOP)?.trim().orEmpty()
        if (emailDoDesktop.isNotBlank() && Patterns.EMAIL_ADDRESS.matcher(emailDoDesktop).matches()) {
            campoEmail.setText(emailDoDesktop)
            validarEmail(emailDoDesktop)
        }
    }

    private fun montarInterface() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0E1524"))
            setPadding(56, 96, 56, 56)
        }

        val titulo = TextView(this).apply {
            text = "Oficina de Pesca"
            setTextColor(Color.parseColor("#F39C12"))
            textSize = 26f
            setTypeface(typeface, Typeface.BOLD)
        }

        val subtitulo = TextView(this).apply {
            text = getString(R.string.identificacao_subtitulo)
            setTextColor(Color.parseColor("#B8C0CC"))
            textSize = 15f
            setPadding(0, 24, 0, 32)
        }

        campoEmail = EditText(this).apply {
            hint = getString(R.string.identificacao_email_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            setTextColor(Color.WHITE)
            setHintTextColor(Color.parseColor("#7A8699"))
            setBackgroundColor(Color.parseColor("#1A2535"))
            setPadding(32, 28, 32, 28)
            setSingleLine(true)
        }

        textoMensagem = TextView(this).apply {
            setTextColor(Color.parseColor("#FCA5A5"))
            textSize = 13f
            setPadding(0, 16, 0, 0)
            visibility = View.GONE
        }

        progresso = ProgressBar(this).apply {
            visibility = View.GONE
        }

        textoPlanos = TextView(this).apply {
            text = getString(R.string.identificacao_planos_validos)
            setTextColor(Color.parseColor("#B8C0CC"))
            textSize = 13f
            setPadding(0, 18, 0, 0)
            visibility = View.GONE
        }

        botaoPlanos = Button(this).apply {
            text = getString(R.string.identificacao_comprar_ativar)
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#2563EB"))
            setPadding(0, 24, 0, 24)
            visibility = View.GONE
            setOnClickListener { abrirPlanosNoNavegador() }
        }

        botaoEntrar = Button(this).apply {
            text = getString(R.string.identificacao_entrar)
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#27AE60"))
            setPadding(0, 28, 0, 28)
            setOnClickListener {
                val email = campoEmail.text.toString().trim()
                if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
                    exibirMensagem(getString(R.string.identificacao_email_invalido), mostrarPlanos = false)
                    return@setOnClickListener
                }
                validarEmail(email)
            }
        }

        val botaoWrapper = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(0, 32, 0, 0)
            addView(progresso)
        }

        root.addView(titulo)
        root.addView(subtitulo)
        root.addView(campoEmail)
        root.addView(textoMensagem)
        root.addView(textoPlanos)
        root.addView(
            botaoPlanos,
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                topMargin = 18
            },
        )
        root.addView(
            botaoEntrar,
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                topMargin = 32
            },
        )
        root.addView(botaoWrapper)

        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun exibirMensagem(mensagem: String, mostrarPlanos: Boolean = true) {
        textoMensagem.text = mensagem
        textoMensagem.visibility = View.VISIBLE
        textoPlanos.visibility = if (mostrarPlanos) View.VISIBLE else View.GONE
        botaoPlanos.visibility = if (mostrarPlanos) View.VISIBLE else View.GONE
    }

    private fun definirCarregando(carregando: Boolean) {
        botaoEntrar.isEnabled = !carregando
        progresso.visibility = if (carregando) View.VISIBLE else View.GONE
    }

    private fun validarEmail(email: String) {
        definirCarregando(true)
        textoMensagem.visibility = View.GONE
        textoPlanos.visibility = View.GONE
        botaoPlanos.visibility = View.GONE

        Thread {
            val resultado = consultarStatusLicencaPorEmail(email)
            runOnUiThread {
                definirCarregando(false)
                if (resultado.payload == null) {
                    val mensagem = getString(R.string.identificacao_falha_conexao_detalhada, resultado.diagnostico.ifBlank { "sem detalhes" })
                    exibirMensagem(mensagem, mostrarPlanos = false)
                    return@runOnUiThread
                }
                val payload = resultado.payload
                val ativa = payload.optBoolean("ativa", false)
                if (ativa && !licencaEhTrial(payload)) {
                    salvarEmailValidado(email)
                    abrirSistemaPrincipal()
                } else {
                    limparEmailValidado()
                    val mensagem = if (licencaEhTrial(payload)) {
                        getString(R.string.identificacao_trial_bloqueado)
                    } else {
                        getString(R.string.identificacao_licenca_inativa)
                    }
                    exibirMensagem(mensagem)
                }
            }
        }.start()
    }

    private fun licencaEhTrial(resultado: JSONObject): Boolean {
        val campos = listOf("tipo", "plano", "status", "mensagem")
        return campos.any { chave ->
            resultado.optString(chave, "").trim().uppercase(Locale.ROOT).contains("TRIAL")
        }
    }

    private fun urlPlanosRegional(): String {
        val locale = Locale.getDefault()
        val idioma = locale.language.lowercase(Locale.ROOT)
        val pais = locale.country.uppercase(Locale.ROOT)
        return if (pais == "BR" || idioma == "PT") {
            "https://www.frssolutions.com.br/planos"
        } else {
            "https://www.frssolutions.com.br/plans"
        }
    }

    private fun abrirPlanosNoNavegador() {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(urlPlanosRegional())))
        } catch (exc: Exception) {
            Log.w(TAG, "Falha ao abrir planos no navegador: ${exc.message}")
            exibirMensagem(getString(R.string.identificacao_falha_abrir_planos), mostrarPlanos = true)
        }
    }

    private fun consultarStatusLicencaPorEmail(email: String): ResultadoLicenca {
        val baseUrl = BuildConfig.LICENSE_API_BASE_URL.trim().trimEnd('/')
        if (baseUrl.isBlank()) {
            Log.w(TAG, "LICENSE_API_BASE_URL não configurada no build.")
            return ResultadoLicenca(null, "LICENSE_API_BASE_URL vazio no BuildConfig")
        }
        val emailCodificado = URLEncoder.encode(email, "UTF-8")
        val rotas = listOf(
            "/licencas/status-email",
            "/api/licencas/status-email",
        )
        val diagnosticos = mutableListOf<String>()

        for (rota in rotas) {
            val urlCompleta = "$baseUrl$rota?email=$emailCodificado"
            val resultado = consultarUrlLicenca(URL(urlCompleta))
            if (resultado.payload != null) {
                return resultado
            }
            diagnosticos.add(resultado.diagnostico)
        }

        return ResultadoLicenca(null, diagnosticos.joinToString("\n\n"))
    }

    private fun consultarUrlLicenca(url: URL): ResultadoLicenca {
        var conexao: HttpURLConnection? = null
        return try {
            conexao = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 30000
                readTimeout = 30000
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", "OficinaPescaMobile/${BuildConfig.VERSION_NAME}")
            }
            val codigo = conexao.responseCode
            val leitor = if (codigo in 200..299) conexao.inputStream else conexao.errorStream
            val corpo = leitor?.let { BufferedReader(InputStreamReader(it)).use { reader -> reader.readText() } }.orEmpty()
            val diagnostico = "URL: $url\nHTTP $codigo\nResposta: ${corpo.take(500).ifBlank { "<vazia>" }}"
            Log.w(TAG, diagnostico)
            if (codigo in 200..299) {
                ResultadoLicenca(JSONObject(corpo), diagnostico)
            } else {
                ResultadoLicenca(null, diagnostico)
            }
        } catch (exc: Exception) {
            val diagnostico = "URL: $url\nErro: ${exc.javaClass.simpleName}\nMensagem: ${exc.message ?: "sem mensagem"}"
            Log.w(TAG, diagnostico, exc)
            ResultadoLicenca(null, diagnostico)
        } finally {
            conexao?.disconnect()
        }
    }

    private fun salvarEmailValidado(email: String) {
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_EMAIL_VALIDADO, email)
            .apply()
    }

    private fun limparEmailValidado() {
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_EMAIL_VALIDADO)
            .apply()
    }

    private fun abrirSistemaPrincipal() {
        startActivity(
            Intent(this, SistemaPrincipalActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            },
        )
        finish()
    }
}
