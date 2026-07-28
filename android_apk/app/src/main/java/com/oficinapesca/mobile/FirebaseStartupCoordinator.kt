package com.oficinapesca.mobile

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import com.google.firebase.FirebaseApp
import com.google.firebase.database.DataSnapshot
import com.google.firebase.database.DatabaseError
import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ServerValue
import com.google.firebase.database.ValueEventListener
import java.util.Locale

object FirebaseStartupCoordinator {
    private const val TAG = "OficinaPesca"
    private const val AUTH_TIMEOUT_MS = 15000L

    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile
    private var attemptId = 0L

    private var timeoutRunnable: Runnable? = null

    fun start(context: Context) {
        attemptId += 1
        val attempt = attemptId
        val appContext = context.applicationContext
        val deviceId = obterDeviceId(appContext)

        StartupConnectionState.setConnecting()
        iniciarWatchdog(attempt)

        Log.i(
            TAG,
            "[auth:$attempt] Iniciando validação Firebase em background. channel='${BuildConfig.FIREBASE_SYNC_CHANNEL}', " +
                "authPath='${BuildConfig.FIREBASE_AUTH_PATH}', deviceId='$deviceId'",
        )

        try {
            if (FirebaseApp.getApps(appContext).isEmpty()) {
                FirebaseApp.initializeApp(appContext)
                Log.i(TAG, "[auth:$attempt] FirebaseApp.initializeApp executado em background.")
            }
            if (FirebaseApp.getApps(appContext).isEmpty()) {
                atualizarErro("Firebase não inicializado. Verifique google-services.json no módulo app.", attempt)
                return
            }
        } catch (exc: Exception) {
            atualizarErro("Falha ao inicializar Firebase: ${exc.message}", attempt)
            return
        }

        val database = FirebaseDatabase.getInstance()
        database.goOnline()
        val authBase = BuildConfig.FIREBASE_AUTH_PATH.trim().ifBlank { "mobile_auth" }
        val channel = BuildConfig.FIREBASE_SYNC_CHANNEL.trim().ifBlank { "global" }
        val paths = listOf(
            "$authBase/$deviceId",
            "$authBase/$channel/$deviceId",
            "$authBase/global/$deviceId",
            "$authBase/default",
        )

        Log.i(TAG, "[auth:$attempt] Paths candidatos: $paths")
        verificarPathAuth(database, appContext, deviceId, authBase, channel, paths, 0, attempt)
    }

    private fun iniciarWatchdog(attempt: Long) {
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = Runnable {
            if (attempt != attemptId) {
                return@Runnable
            }
            Log.w(TAG, "[auth:$attempt] Timeout de autenticação após ${AUTH_TIMEOUT_MS}ms.")
            atualizarErro(
                "Tempo limite ao validar acesso no Firebase. Verifique conexão/regras e tente novamente.",
                attempt,
            )
        }
        mainHandler.postDelayed(timeoutRunnable!!, AUTH_TIMEOUT_MS)
    }

    private fun cancelarWatchdog() {
        timeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        timeoutRunnable = null
    }

    private fun verificarPathAuth(
        database: FirebaseDatabase,
        context: Context,
        deviceId: String,
        authBase: String,
        channel: String,
        paths: List<String>,
        index: Int,
        attempt: Long,
    ) {
        if (attempt != attemptId) {
            Log.i(TAG, "[auth:$attempt] Callback descartado por tentativa obsoleta.")
            return
        }

        if (index >= paths.size) {
            Log.i(TAG, "[auth:$attempt] Nenhum path autorizado. Iniciando auto-cadastro global.")
            tentarAutoCadastroGlobal(database, deviceId, authBase, channel, attempt)
            return
        }

        val path = paths[index]
        Log.i(TAG, "[auth:$attempt] Verificando path ${index + 1}/${paths.size}: $path")
        database.reference.child(path).addListenerForSingleValueEvent(object : ValueEventListener {
            override fun onDataChange(snapshot: DataSnapshot) {
                if (attempt != attemptId) {
                    Log.i(TAG, "[auth:$attempt] onDataChange ignorado (tentativa obsoleta).")
                    return
                }
                if (snapshot.exists() && autorizado(snapshot)) {
                    Log.i(TAG, "[auth:$attempt] Path autorizado: $path")
                    atualizarOk(attempt)
                } else {
                    Log.i(TAG, "[auth:$attempt] Path não autorizado/ausente: $path")
                    verificarPathAuth(database, context, deviceId, authBase, channel, paths, index + 1, attempt)
                }
            }

            override fun onCancelled(error: DatabaseError) {
                if (attempt != attemptId) {
                    Log.i(TAG, "[auth:$attempt] onCancelled ignorado (tentativa obsoleta).")
                    return
                }
                val msg = "Falha Firebase em '$path': ${error.message}"
                Log.w(TAG, "[auth:$attempt] $msg")
                if (index >= paths.lastIndex) {
                    Log.i(TAG, "[auth:$attempt] Último path cancelado. Tentando auto-cadastro.")
                    tentarAutoCadastroGlobal(database, deviceId, authBase, channel, attempt)
                    return
                }
                verificarPathAuth(database, context, deviceId, authBase, channel, paths, index + 1, attempt)
            }
        })
    }

    private fun tentarAutoCadastroGlobal(
        database: FirebaseDatabase,
        deviceId: String,
        authBase: String,
        channel: String,
        attempt: Long,
    ) {
        if (attempt != attemptId) {
            Log.i(TAG, "[auth:$attempt] Auto-cadastro abortado (tentativa obsoleta).")
            return
        }

        val destino = "$authBase/global/$deviceId"
        Log.i(TAG, "[auth:$attempt] Iniciando auto-cadastro em '$destino'.")

        val payload = hashMapOf<String, Any>(
            "ativa" to true,
            "enabled" to true,
            "status" to "liberado",
            "modo_teste" to true,
            "canal" to "global",
            "canal_origem" to channel,
            "device_id" to deviceId,
            "app_version" to BuildConfig.VERSION_NAME,
            "base_desktop" to BuildConfig.VERSION_NAME,
            "origem" to "auto_cadastro_apk",
            "updated_at" to ServerValue.TIMESTAMP,
        )

        database.reference.child(destino).updateChildren(payload)
            .addOnSuccessListener {
                if (attempt != attemptId) {
                    Log.i(TAG, "[auth:$attempt] Sucesso de auto-cadastro ignorado (tentativa obsoleta).")
                    return@addOnSuccessListener
                }
                Log.i(TAG, "[auth:$attempt] Auto-cadastro concluído com sucesso em '$destino'.")
                atualizarOk(attempt)
            }
            .addOnFailureListener { exc ->
                if (attempt != attemptId) {
                    Log.i(TAG, "[auth:$attempt] Falha de auto-cadastro ignorada (tentativa obsoleta).")
                    return@addOnFailureListener
                }
                atualizarErro(
                    "Acesso não autorizado no Firebase para este dispositivo e falha no auto-cadastro: ${exc.message}",
                    attempt,
                )
            }
    }

    private fun autorizado(snapshot: DataSnapshot): Boolean {
        val ativa = snapshot.child("ativa").getValue(Boolean::class.java) == true
        val enabled = snapshot.child("enabled").getValue(Boolean::class.java) == true
        val status = (snapshot.child("status").getValue(String::class.java) ?: "").trim().lowercase(Locale.ROOT)
        val statusOk = status in setOf("ativo", "active", "liberado", "ok")

        val baseDesktop = (snapshot.child("base_desktop").getValue(String::class.java) ?: "").trim()
        val compatDesktop = baseDesktop.isBlank() || baseDesktop == BuildConfig.VERSION_NAME

        return (ativa || enabled || statusOk) && compatDesktop
    }

    private fun atualizarOk(attempt: Long) {
        cancelarWatchdog()
        StartupConnectionState.setOk()
        Log.i(TAG, "[auth:$attempt] Acesso autorizado.")
    }

    private fun atualizarErro(msg: String, attempt: Long) {
        if (attempt != attemptId) {
            Log.i(TAG, "[auth:$attempt] Erro descartado por tentativa obsoleta: $msg")
            return
        }
        cancelarWatchdog()
        StartupConnectionState.setError(msg)
        Log.w(TAG, "[auth:$attempt] $msg")
    }

    private fun obterDeviceId(context: Context): String {
        return (Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "desconhecido").trim()
    }
}