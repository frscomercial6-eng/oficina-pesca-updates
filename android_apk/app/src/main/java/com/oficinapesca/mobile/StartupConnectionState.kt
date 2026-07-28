package com.oficinapesca.mobile

data class StartupConnectionSnapshot(
    val state: String,
    val message: String,
    val dotColor: String,
)

object StartupConnectionState {
    @Volatile
    private var snapshot = StartupConnectionSnapshot(
        state = "connecting",
        message = "Conectando",
        dotColor = "#F59E0B",
    )

    fun current(): StartupConnectionSnapshot = snapshot

    fun setConnecting(message: String = "Conectando") {
        update("connecting", message, "#F59E0B")
    }

    fun setOk(message: String = "Conectado") {
        update("ok", message, "#22C55E")
    }

    fun setError(message: String = "Erro de Conexão") {
        update("error", message, "#EF4444")
    }

    private fun update(state: String, message: String, dotColor: String) {
        snapshot = StartupConnectionSnapshot(
            state = state,
            message = message,
            dotColor = dotColor,
        )
    }
}