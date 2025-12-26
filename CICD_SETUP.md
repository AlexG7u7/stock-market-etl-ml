# 🚀 Resumen de Configuración CI/CD

## ✅ Archivos Creados

### GitHub Actions Workflows
```
.github/workflows/
├── deploy.yml          # Despliegue automático a producción
└── ci.yml             # Tests y validación (PR y develop)
```

### Documentación
```
docs/GITHUB_ACTIONS_SETUP.md   # Guía completa de configuración
scripts/init_git.sh            # Script de inicialización
```

---

## 🔐 Secretos a Crear en GitHub

Ve a: `https://github.com/stock-market-bot/stock-market-etl-ml/settings/secrets/actions`

| Nombre | Valor | Descripción |
|--------|-------|-------------|
| `SSH_PRIVATE_KEY` | Contenido de `~/.ssh/id_rsa` | Clave SSH privada |
| `SSH_HOST` | `ssh.rod-b-op.com` | Hostname del servidor |
| `SSH_USER` | `rodri` | Usuario SSH |
| `SQL_USER` | `rodrigo` | Usuario SQL Server |
| `SQL_PASSWORD` | `rodrigo` | Password SQL Server |

---

## 📋 Pasos para Activar CI/CD

### 1. Obtener tu clave SSH privada
```bash
cat ~/.ssh/id_rsa
```

Copia TODO el contenido (incluye BEGIN y END)

### 2. Configurar Git
```bash
cd /Users/rod/Projects/stock-market
./scripts/init_git.sh
```

O manualmente:
```bash
git init
git remote add origin git@github.com:stock-market-bot/stock-market-etl-ml.git
git add .
git commit -m "Initial commit with CI/CD"
git push -u origin main
```

### 3. Crear los 5 secretos en GitHub
1. Ve a Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Crea cada uno de los 5 secretos de la tabla anterior

### 4. ¡Listo! 
Cada `git push origin main` desplegará automáticamente 🎉

---

## 🎯 Flujo de Trabajo

### Desarrollo con Feature Branch
```bash
# Crear rama nueva
git checkout -b feature/nueva-funcionalidad

# Hacer cambios...
git add .
git commit -m "Add nueva funcionalidad"
git push origin feature/nueva-funcionalidad

# Crear Pull Request en GitHub
# ✅ CI se ejecutará automáticamente (tests, linting)
# ✅ Merge a main → Deploy automático!
```

### Deploy Directo a Main
```bash
# Hacer cambios...
git add .
git commit -m "Update schema"
git push origin main

# 🚀 Deploy automático al servidor!
```

---

## 📊 Monitoreo

### Ver Logs de Deploy
1. Ve a `https://github.com/stock-market-bot/stock-market-etl-ml/actions`
2. Click en el workflow que se está ejecutando
3. Verás logs en tiempo real de cada paso

### Verificar en el Servidor
```bash
ssh rodri@ssh.rod-b-op.com
cd C:\Projects\stock-market
dir  # Ver archivos actualizados
```

---

## 🛠️ Workflows Configurados

### Deploy (`deploy.yml`)
**Trigger:** Push a `main`

**Pasos:**
1. ✅ Checkout código
2. ✅ Setup SSH
3. ✅ Deploy archivos (SCP)
4. ✅ Ejecutar SQL (si cambió)
5. ✅ Notificar resultado

### CI (`ci.yml`)
**Trigger:** Pull Requests a `main` o push a `develop`

**Pasos:**
1. ✅ Checkout código
2. ✅ Setup Python 3.11
3. ✅ Install dependencies
4. ✅ Lint (black, pylint)
5. ✅ Run tests (pytest)
6. ✅ Validate SQL syntax

---

## 🔄 Rollback

Si algo sale mal:

```bash
# Ver commits anteriores
git log --oneline

# Volver a un commit específico
git revert <commit-hash>
git push origin main

# O forzar rollback
git reset --hard <commit-hash>
git push -f origin main
```

---

## 📝 Tips

### Ejecución Manual
Puedes ejecutar workflows manualmente desde GitHub:
1. Actions → Deploy to Windows Server
2. Run workflow → Elegir rama → Run workflow

### Solo Deploy de SQL
Si solo quieres actualizar la BD:
```bash
git add sql/
git commit -m "Update schema only"
git push origin main
```
El workflow detectará que solo cambió SQL y ejecutará solo ese paso.

### Saltarse el Deploy
Si quieres commitear sin desplegar:
```bash
git commit -m "Work in progress [skip ci]"
```

---

## ✅ Checklist Final

- [ ] Clave SSH copiada
- [ ] 5 secretos creados en GitHub
- [ ] Git inicializado y remote configurado
- [ ] Primer push hecho
- [ ] Workflow ejecutado exitosamente
- [ ] Archivos verificados en servidor

---

¡Ya tienes CI/CD profesional! 🚀
