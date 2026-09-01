package com.oficinapesca.mobile

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate

class MainActivity : AppCompatActivity() {
    companion object {
        private const val TAG = "OficinaPesca"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        Log.i(TAG, "Inicializando APK nativo Oficina de Pesca v${BuildConfig.VERSION_NAME}")

        setContentView(View(this).apply {
            setBackgroundColor(Color.parseColor("#0E1524"))
        })

        val emailValidado = getSharedPreferences(IdentificacaoActivity.PREFS_NAME, MODE_PRIVATE)
            .getString(IdentificacaoActivity.KEY_EMAIL_VALIDADO, null)

        Log.i(TAG, "Revalidando licença móvel antes de abrir telas operacionais.")
        startActivity(
            Intent(this, IdentificacaoActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                intent.getStringExtra(IdentificacaoActivity.EXTRA_EMAIL_DESKTOP)?.let { emailDesktop ->
                    putExtra(IdentificacaoActivity.EXTRA_EMAIL_DESKTOP, emailDesktop)
                } ?: emailValidado?.let { emailSalvo ->
                    putExtra(IdentificacaoActivity.EXTRA_EMAIL_DESKTOP, emailSalvo)
                }
            }
        )
        finish()
    }
}