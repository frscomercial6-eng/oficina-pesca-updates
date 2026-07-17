package com.oficinapesca.mobile

import android.graphics.Color
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import com.google.firebase.FirebaseApp
import com.google.firebase.database.DataSnapshot
import com.google.firebase.database.DatabaseError
import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ValueEventListener
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var tituloView: TextView
    private lateinit var statusView: TextView
    private lateinit var detalhesView: TextView
    private lateinit var botaoTentar: Button

    private val deviceId: String by lazy {
        (Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "desconhecido").trim()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        Log.i("OficinaPesca", "Inicializando APK nativo Oficina de Pesca v${BuildConfig.VERSION_NAME}")

        montarInterfaceNativa()
        validarAcessoViaFirebase()
    }

    private fun montarInterfaceNativa() {
        val root = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#0E1524"))
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(28), dp(20), dp(28))
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }

        tituloView = TextView(this).apply {
            text = "Oficina de Pesca"
            setTextColor(Color.parseColor("#93C5FD"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            gravity = Gravity.CENTER
        }

        val versaoView = TextView(this).apply {
            text = "v${BuildConfig.VERSION_NAME}"
            setTextColor(Color.parseColor("#FCD34D"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            gravity = Gravity.CENTER
        }

        statusView = TextView(this).apply {
            text = "Conectando ao Firebase Realtime Database..."
            setTextColor(Color.parseColor("#E5E7EB"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            gravity = Gravity.CENTER
            setPadding(0, dp(22), 0, dp(14))
        }

        detalhesView = TextView(this).apply {
            text = "Canal: ${BuildConfig.FIREBASE_SYNC_CHANNEL}\nDispositivo: $deviceId"
            setTextColor(Color.parseColor("#9CA3AF"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            gravity = Gravity.CENTER
            setLineSpacing(0f, 1.1f)
        }

        botaoTentar = Button(this).apply {
            text = "Tentar novamente"
            isAllCaps = false
            visibility = Button.GONE
            setOnClickListener {
                visibility = Button.GONE
                validarAcessoViaFirebase()
            }
        }

        container.addView(tituloView)
        container.addView(versaoView)
        container.addView(statusView)
        container.addView(detalhesView)
        container.addView(botaoTentar)
        root.addView(container)
        setContentView(root)
    }

    private fun validarAcessoViaFirebase() {
        statusView.text = "Conectando ao Firebase Realtime Database..."
        statusView.setTextColor(Color.parseColor("#E5E7EB"))
        detalhesView.text = "Canal: ${BuildConfig.FIREBASE_SYNC_CHANNEL}\nDispositivo: $deviceId"

        try {
            if (FirebaseApp.getApps(this).isEmpty()) {
                FirebaseApp.initializeApp(this)
            }
            if (FirebaseApp.getApps(this).isEmpty()) {
                atualizarStatusErro("Firebase não inicializado. Verifique google-services.json no módulo app.")
                return
            }
        } catch (exc: Exception) {
            atualizarStatusErro("Falha ao inicializar Firebase: ${exc.message}")
            return
        }

        val database = FirebaseDatabase.getInstance()
        val authBase = BuildConfig.FIREBASE_AUTH_PATH.trim().ifBlank { "mobile_auth" }
        val channel = BuildConfig.FIREBASE_SYNC_CHANNEL.trim().ifBlank { "global" }
        val paths = listOf(
            "$authBase/$deviceId",
            "$authBase/$channel/$deviceId",
            "$authBase/global/$deviceId",
            "$authBase/default",
        )

        verificarPathAuth(database, paths, 0)
    }

    private fun verificarPathAuth(database: FirebaseDatabase, paths: List<String>, index: Int) {
        if (index >= paths.size) {
            atualizarStatusErro("Acesso não autorizado no Firebase para este dispositivo.")
            return
        }

        val path = paths[index]
        database.reference.child(path).addListenerForSingleValueEvent(object : ValueEventListener {
            override fun onDataChange(snapshot: DataSnapshot) {
                if (snapshot.exists() && autorizado(snapshot)) {
                    atualizarStatusOk(path, snapshot)
                } else {
                    verificarPathAuth(database, paths, index + 1)
                }
            }

            override fun onCancelled(error: DatabaseError) {
                val msg = "Falha Firebase em '$path': ${error.message}"
                Log.w("OficinaPesca", msg)
                if (index >= paths.lastIndex) {
                    atualizarStatusErro(msg)
                    return
                }
                verificarPathAuth(database, paths, index + 1)
            }
        })
    }

    private fun autorizado(snapshot: DataSnapshot): Boolean {
        val ativa = snapshot.child("ativa").getValue(Boolean::class.java) == true
        val enabled = snapshot.child("enabled").getValue(Boolean::class.java) == true
        val status = (snapshot.child("status").getValue(String::class.java) ?: "").trim().lowercase(Locale.ROOT)
        val statusOk = status in setOf("ativo", "active", "liberado", "ok")

        val baseDesktop = (snapshot.child("base_desktop").getValue(String::class.java) ?: "").trim()
        val compatDesktop = baseDesktop.isBlank() || baseDesktop == "1.0.48"

        return (ativa || enabled || statusOk) && compatDesktop
    }

    private fun atualizarStatusOk(path: String, snapshot: DataSnapshot) {
        val cliente = (snapshot.child("cliente").getValue(String::class.java) ?: "").trim()
        statusView.text = "Acesso liberado via Firebase"
        statusView.setTextColor(Color.parseColor("#34D399"))
        detalhesView.text = buildString {
            append("Canal: ${BuildConfig.FIREBASE_SYNC_CHANNEL}\n")
            append("Path validado: $path\n")
            append("Dispositivo: $deviceId")
            if (cliente.isNotBlank()) {
                append("\nCliente: $cliente")
            }
        }
        botaoTentar.visibility = Button.GONE
    }

    private fun atualizarStatusErro(msg: String) {
        statusView.text = "Acesso bloqueado"
        statusView.setTextColor(Color.parseColor("#F87171"))
        detalhesView.text = "$msg\nCanal: ${BuildConfig.FIREBASE_SYNC_CHANNEL}\nDispositivo: $deviceId"
        botaoTentar.visibility = Button.VISIBLE
        Log.w("OficinaPesca", msg)
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }
}
