package dev.edilson.wololo.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AccessKeyStore(context: Context) {
    private val preferences = context.getSharedPreferences("credentials", Context.MODE_PRIVATE)
    private val alias = "dev.edilson.wololo.access"

    @Synchronized
    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
        }.generateKey()
    }

    fun read(server: String): String {
        val encrypted = preferences.getString(identifier(server), null) ?: return ""
        val pieces = encrypted.split(':', limit = 2)
        check(pieces.size == 2) { "The saved access key could not be read. Save it again in Settings." }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, Base64.decode(pieces[0], Base64.NO_WRAP)))
        return String(cipher.doFinal(Base64.decode(pieces[1], Base64.NO_WRAP)), Charsets.UTF_8)
    }

    fun write(server: String, value: String) {
        if (value.isBlank()) {
            check(preferences.edit().remove(identifier(server)).commit())
            return
        }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val encrypted = cipher.doFinal(value.trim().toByteArray(Charsets.UTF_8))
        val content = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(encrypted, Base64.NO_WRAP)
        check(preferences.edit().putString(identifier(server), content).commit())
    }

    private fun identifier(server: String) = MessageDigest.getInstance("SHA-256")
        .digest(server.toByteArray()).joinToString("") { "%02x".format(it) }
}
