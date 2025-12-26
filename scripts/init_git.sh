#!/bin/bash

# ==============================================================================
# Script de Inicialización de Git y Primer Deploy
# ==============================================================================

set -e  # Exit on error

echo "🚀 Inicializando repositorio Git..."

# Verificar si ya está inicializado
if [ -d .git ]; then
    echo "✓ Git ya está inicializado"
else
    git init
    echo "✓ Git inicializado"
fi

# Configurar remote
REPO_URL="git@github.com:stock-market-bot/stock-market-etl-ml.git"

if git remote | grep -q "origin"; then
    echo "✓ Remote 'origin' ya existe"
    git remote set-url origin $REPO_URL
else
    git remote add origin $REPO_URL
    echo "✓ Remote 'origin' configurado: $REPO_URL"
fi

# Verificar rama actual
CURRENT_BRANCH=$(git branch --show-current)
if [ -z "$CURRENT_BRANCH" ]; then
    git checkout -b main
    echo "✓ Rama 'main' creada"
else
    echo "✓ En rama: $CURRENT_BRANCH"
fi

# Agregar todos los archivos
echo "📦 Agregando archivos..."
git add .

# Verificar qué se va a commitear
echo ""
echo "📋 Archivos que se van a commitear:"
git status --short

# Hacer commit
echo ""
read -p "¿Deseas hacer commit? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Mensaje del commit: " COMMIT_MSG
    git commit -m "$COMMIT_MSG"
    echo "✓ Commit creado"
    
    # Push
    echo ""
    read -p "¿Deseas hacer push a GitHub? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🚀 Haciendo push..."
        git push -u origin main
        echo ""
        echo "✅ ¡Código subido a GitHub!"
        echo ""
        echo "📝 PRÓXIMOS PASOS:"
        echo "1. Ve a: https://github.com/stock-market-bot/stock-market-etl-ml/settings/secrets/actions"
        echo "2. Crea los secretos según docs/GITHUB_ACTIONS_SETUP.md"
        echo "3. Ve a Actions para ver el despliegue: https://github.com/stock-market-bot/stock-market-etl-ml/actions"
    fi
fi

echo ""
echo "✅ ¡Listo!"
