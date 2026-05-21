# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Firebase
-keep class com.google.firebase.** { *; }

# ML Kit
-keep class com.google.mlkit.** { *; }

# Hilt
-keep class dagger.hilt.** { *; }
-keep @dagger.hilt.android.lifecycle.HiltViewModel class * { *; }
