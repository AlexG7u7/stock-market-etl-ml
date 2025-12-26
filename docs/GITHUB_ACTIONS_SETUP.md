# 🚀 Configuración de GitHub Actions - Despliegue Automático

## 📋 Secretos Requeridos en GitHub

Debes crear los siguientes **GitHub Secrets** en tu repositorio:

### Cómo crear secretos:
1. Ve a tu repositorio: `https://github.com/stock-market-bot/stock-market-etl-ml`
2. Click en **Settings** → **Secrets and variables** → **Actions**
3. Click en **New repository secret**
4. Crea cada uno de estos secretos:

---

### 🔑 Secretos de SSH (Conexión al Servidor)

#### `SSH_PRIVATE_KEY`
**Descripción:** Tu clave SSH privada para conectarte al servidor Windows  
**Valor:** El contenido completo de tu archivo `~/.ssh/id_rsa`

**Cómo obtenerlo:**
```bash
cat ~/.ssh/id_rsa
```

Copia TODO el contenido (incluyendo `-----BEGIN OPENSSH PRIVATE KEY-----` y `-----END OPENSSH PRIVATE KEY-----`)

⚠️ **IMPORTANTE:** Asegúrate de que el servidor tenga tu clave pública en `~/.ssh/authorized_keys`

---

#### `SSH_HOST`
**Descripción:** Hostname del servidor Windows  
**Valor:** 
```
ssh.rod-b-op.com
```

---

#### `SSH_USER`
**Descripción:** Usuario SSH del servidor  
**Valor:** 
```
rodri
```

---

### 🗄️ Secretos de SQL Server

#### `SQL_USER`
**Descripción:** Usuario de SQL Server  
**Valor:** 
```
rodrigo
```

---

#### `SQL_PASSWORD`
**Descripción:** Contraseña de SQL Server  
**Valor:** 
```
rodrigo
```

---

## 🎯 Workflows Configurados

### 1. **Deploy to Windows Server** (`deploy.yml`)
- **Trigger:** Cada `git push` a la rama `main`
- **Acciones:**
  - ✅ Descarga el código del repositorio
  - ✅ Configura la conexión SSH
  - ✅ Copia archivos al servidor vía SCP
  - ✅ Ejecuta el script SQL si hay cambios en `/sql/`
  - ✅ Notifica el resultado

**Uso:**
```bash
git add .
git commit -m "Update schema"
git push origin main
# 🚀 Se desplegará automáticamente!
```

---

### 2. **CI - Tests and Validation** (`ci.yml`)
- **Trigger:** Pull requests a `main` o push a `develop`
- **Acciones:**
  - ✅ Instala dependencias Python
  - ✅ Ejecuta linter (black, pylint)
  - ✅ Ejecuta tests con pytest
  - ✅ Valida sintaxis de archivos SQL

**Uso:**
```bash
git checkout -b feature/nueva-funcionalidad
git add .
git commit -m "Add new feature"
git push origin feature/nueva-funcionalidad
# Crea un Pull Request en GitHub
# ✅ Los tests se ejecutarán automáticamente
```

---

## 📝 Ejecución Manual

También puedes ejecutar el workflow manualmente:

1. Ve a **Actions** en GitHub
2. Selecciona **Deploy to Windows Server**
3. Click en **Run workflow**
4. Elige la rama y click **Run workflow**

---

## 🔍 Verificar el Despliegue

Después de cada push, puedes ver el progreso:

1. Ve a **Actions** en GitHub
2. Click en el workflow en ejecución
3. Verás logs en tiempo real de cada paso

---

## 🛠️ Troubleshooting

### Error: "Permission denied (publickey)"
- Verifica que `SSH_PRIVATE_KEY` esté completo
- Asegúrate de que la clave pública esté en el servidor

### Error: "Login failed for user"
- Verifica `SQL_USER` y `SQL_PASSWORD`
- Prueba la conexión manualmente primero

### Error: "No such file or directory"
- Verifica que el directorio `C:/Projects/stock-market/` exista en el servidor

---

## ✅ Checklist de Configuración

- [ ] Crear secreto `SSH_PRIVATE_KEY`
- [ ] Crear secreto `SSH_HOST`
- [ ] Crear secreto `SSH_USER`
- [ ] Crear secreto `SQL_USER`
- [ ] Crear secreto `SQL_PASSWORD`
- [ ] Hacer primer commit y push
- [ ] Verificar que el workflow se ejecute correctamente
- [ ] Confirmar que los archivos estén en el servidor

---

## 🎉 ¡Listo!

Una vez configurados los secretos, cada vez que hagas:

```bash
git push origin main
```

El código se desplegará automáticamente al servidor Windows! 🚀
