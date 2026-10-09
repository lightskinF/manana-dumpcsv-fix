# Compilare Manana: problemi trovati (Windows, Android Studio recente)

Fatti compilando `MANANA-app` da Codeberg il 10 ottobre 2026. Il progetto richiede plugin Android 8.1.4, NDK
26.1.10909125, CMake 3.22.1.

## 1. Manca la cartella `gradle/` (wrapper)
`gradle/` è nel `.gitignore`, quindi non c'è la versione di Gradle. Android Studio usa la sua, troppo nuova:
`Unable to find method ... DependencyHandler.module(...)`. Creare `gradle/wrapper/gradle-wrapper.properties` con
`distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip`.

## 2. Java troppo nuovo
Con Java 25 (quello di Android Studio recente) Gradle 8.5 dà *Incompatible Gradle JVM version*. In *Settings →
Build Tools → Gradle → Gradle JDK* scaricare e scegliere un JDK 17.

## 3. `app/.cxx` è stata inserita nel repository
La cartella contiene una cache di compilazione con percorsi del computer di chi l'ha prodotta e fa fallire
CMake: `[CXX1409] ... expected buildFiles file 'C:\Users\...\CMakeLists.txt' to exist`. Va cancellata
(`rm -rf app/.cxx`) e dovrebbe essere aggiunta al `.gitignore`.

## 4. Manca `submodules/libpcap/bpf_filter.c`
`CMake Error at pcapd/CMakeLists.txt:16 (ADD_LIBRARY): Cannot find source file`. La copia di libpcap nel
repository è identica alla versione **1.10.1**, tranne per questo file (e `msdos/makefile`). Si ripristina da:

    curl -L -o submodules/libpcap/bpf_filter.c https://raw.githubusercontent.com/the-tcpdump-group/libpcap/libpcap-1.10.1/bpf_filter.c
    sha256sum submodules/libpcap/bpf_filter.c

L'impronta SHA-256 deve essere `3f289eae3b38e2c5250907732a74dadddca1ba84179c88f27d1912ab6f755bf4`.
