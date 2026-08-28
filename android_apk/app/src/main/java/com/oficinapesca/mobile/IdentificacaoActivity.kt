package com.oficinapesca.mobile

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
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

/**
 * Tela de identificação exibida na primeira abertura do APK: pede o e-mail
 * cadastrado da Oficina e valida a assinatura/licença ativa contra a API do
 * Render antes de liberar a tela principal (WebView).
 */
class IdentificacaoActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "OficinaPesca"
        const val PREFS_NAME = "ofp_licenca_prefs"
        const val KEY_EMAIL_VALIDADO = "email_validado"
        const val EXTRA_EMAIL_DESKTOP = "email_desktop"
    }

    private lateinit var campoEmail: EditText
    private lateinit var botaoEntrar: Button
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
            text = "Informe o e-mail cadastrado no sistema Desktop para liberar o aplicativo."
            setTextColor(Color.parseColor("#B8C0CC"))
            textSize = 15f
            setPadding(0, 24, 0, 32)
        }

        campoEmail = EditText(this).apply {
            hint = "seu-email@exemplo.com"
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

        botaoEntrar = Button(this).apply {
            text = "ENTRAR"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#27AE60"))
            setPadding(0, 28, 0, 28)
            setOnClickListener {
                val email = campoEmail.text.toString().trim()
                if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
                    exibirMensagem("Informe um e-mail válido.")
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
        root.addView(
            botaoEntrar,
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                topMargin = 32
            },
        )
        root.addView(botaoWrapper)

        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun exibirMensagem(mensagem: String) {
        textoMensagem.text = mensagem
        textoMensagem.visibility = View.VISIBLE
    }

    private fun definirCarregando(carregando: Boolean) {
        botaoEntrar.isEnabled = !carregando
        progresso.visibility = if (carregando) View.VISIBLE else View.GONE
    }

    private fun validarEmail(email: String) {
        definirCarregando(true)
        textoMensagem.visibility = View.GONE

        Thread {
            val resultado = consultarStatusLicencaPorEmail(email)
            runOnUiThread {
                definirCarregando(false)
                if (resultado == null) {
                    exibirMensagem("Falha de conexão. Verifique a internet e tente novamente.")
                    return@runOnUiThread
                }
                val ativa = resultado.optBoolean("ativa", false)
                if (ativa) {
                    salvarEmailValidado(email)
                    abrirSistemaPrincipal()
                } else {
                    val mensagem = resultado.optString("mensagem", "Licença não encontrada ou expirada.")
                    exibirMensagem(mensagem.ifBlank { "Licença não encontrada ou expirada." })
                }
            }
        }.start()
    }

    private fun consultarStatusLicencaPorEmail(email: String): JSONObject? {
        val baseUrl = BuildConfig.LICENSE_API_BASE_URL.trim().trimEnd('/')
        if (baseUrl.isBlank()) {
            Log.w(TAG, "LICENSE_API_BASE_URL não configurada no build.")
            return null
        }
        val emailCodificado = URLEncoder.encode(email, "UTF-8")
        val url = URL("$baseUrl/api/licencas/status-email?email=$emailCodificado")
        var conexao: HttpURLConnection? = null
        return try {
            conexao = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 12000
                readTimeout = 12000
            }
            val codigo = conexao.responseCode
            val leitor = if (codigo in 200..299) conexao.inputStream else conexao.errorStream
            val corpo = BufferedReader(InputStreamReader(leitor)).use { it.readText() }
            JSONObject(corpo)
        } catch (exc: Exception) {
            Log.w(TAG, "Falha ao consultar status de licença por e-mail: ${exc.message}")
            null
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

    private fun abrirSistemaPrincipal() {
        startActivity(
            Intent(this, SistemaPrincipalActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            },
        )
        finish()
    }
}
