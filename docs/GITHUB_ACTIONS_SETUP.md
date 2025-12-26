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

#### `SSH_PASSWORD`
**Descripción:** Contraseña SSH para autenticación  
**Valor:** Tu contraseña SSH del servidor

⚠️ **IMPORTANTE:** El servidor debe tener Git instalado y el repositorio ya clonado en `C:\Projects\stock-market`

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

## 🎯 Cómo Funciona el Deploy

### Método: Git Pull en el Servidor

En lugar de transferir archivos vía SCP, el servidor hace `git pull`:

1. GitHub Actions se conecta al servidor vía SSH
2. Ejecuta `git pull origin main` en `C:\Projects\stock-market`
3. Si el commit tiene `[sql]` o `[schema]` en el mensaje, ejecuta el schema SQL

### Ventajas de este método:
- ✅ **Simple**: No requiere claves SSH privadas
- ✅ **Rápido**: Solo descarga cambios (no todos los archivos)
- ✅ **Seguro**: Usa autenticación por contraseña
- ✅ **Eficiente**: Git maneja los cambios incrementales

---

## 🎯 Workflows Configurados

### 1. **Deploy to Windows Server** (`deploy.yml`)
- **Trigger:** Cada `git push` a la rama `main`
- **Acciones:**
  1. Conecta al servidor vía SSH
  2. Ejecuta `git pull origin main` en `C:\Projects\stock-market`
  3. Si el commit contiene `[sql]` o `[schema]`, ejecuta el schema SQL
  4. Notifica el resultado

**Uso:**
```bash
# Deploy normal
git commit -m "feat: nueva función"
git push origin main

# Deploy con actualización SQL
git commit -m "feat: nueva tabla [sql]"
git push origin main
# Deploy con actualización SQL
git commit -m "feat: nueva tabla [sql]"
git push origin main
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

### Error: "Permission denied"
- Verifica que `SSH_PASSWORD` esté correctamente configurado
- Asegúrate de que el usuario `rodri` tenga permisos en el servidor

### Error: "Repository not found"
- Verifica que Git esté instalado en el servidor Windows
- Asegúrate de que el repositorio esté clonado en `C:\Projects\stock-market`

### Error: "SQL command failed"
- Verifica que SQL Server esté ejecutándose
- Confirma que `SQL_USER` y `SQL_PASSWORD` sean correctos
- Asegúrate de que el usuario tenga permisos de `db_owner`

---

## ✅ Checklist de Configuración

- [ ] Crear los 5 secretos en GitHub
- [ ] Verificar que Git esté instalado en el servidor
- [ ] Confirmar que el repositorio esté clonado en `C:\Projects\stock-market`
- [ ] Probar conexión SSH al servidor
- [ ] Hacer un commit de prueba con `[sql]` en el mensaje
- [ ] Verificar que el workflow se ejecute correctamente en Actions

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
