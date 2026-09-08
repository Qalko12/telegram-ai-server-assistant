# Как залить проект на GitHub (безопасно)

## ⚠️ ГЛАВНОЕ ПРАВИЛО

**НИКОГДА не коммить файл `.env` с реальными ключами!**

Он уже в `.gitignore`, но проверь перед каждым `git push`.

---

## Пошаговая инструкция

### 1. Проверь, что `.env` не отслеживается

```bash
git ls-files | grep "^\.env$"
# Должно быть пусто (ничего не найдено)
```

Если нашёлся — удаляй из индекса:
```bash
git rm --cached .env
git commit -m "Remove .env from tracking"
```

### 2. Проверь `.env.example` (должен быть, но БЕЗ реальных ключей)

```bash
cat .env.example
```

Должно быть:
```env
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=
# ... остальные пустые
```

**НЕ должно быть:**
```env
TELEGRAM_BOT_TOKEN=123456:ABC...  # ← УДАЛИТЬ!
ANTHROPIC_API_KEY=sk-...          # ← УДАЛИТЬ!
```

### 3. Закоммить изменения

```bash
git add -A
git commit -m "Your commit message"
```

### 4. Проверь ещё раз перед push

```bash
# Покажет, что уйдёт в GitHub
git diff origin/master --stat

# Если в списке есть .env — СТОП, удали его
```

### 5. Заливай

```bash
git push origin master
```

---

## Если случайно закоммитил ключи

**Немедленно:**

1. **Удали файл из истории:**
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   ```

2. **Залей с force:**
   ```bash
   git push origin master --force
   ```

3. **Перевыпусти ВСЕ ключи:**
   - Telegram: @BotFather → `/revoke` → выбери бота → новый токен
   - Anthropic/BuyTokens: в панели провайдера
   - SSH: смени пароль на сервере

---

## Автоматическая проверка перед push (pre-commit hook)

Создай файл `.git/hooks/pre-commit`:

```bash
#!/bin/sh
if git diff --cached --name-only | grep -q "^\.env$"; then
  echo "❌ ОШИБКА: .env закоммичен! Удали его:"
  echo "   git reset HEAD .env"
  exit 1
fi

if git grep --cached -E "sk-[a-zA-Z0-9]{20,}|password.*=.*[^ ]"; then
  echo "❌ ОШИБКА: Похоже на секрет в коде!"
  exit 1
fi
```

Сделай его исполняемым:
```bash
chmod +x .git/hooks/pre-commit
```

Теперь git будет **блокировать коммит**, если в нём есть `.env` или похожие на секреты строки.

---

## Что должно быть в репозитории

✅ **Можно коммитить:**
- Весь код (`.py`, `.yml`, `Dockerfile`)
- `.env.example` (пустой, с комментариями)
- `README.md`, `docs/`, тесты
- `.gitignore`, `.dockerignore`

❌ **НЕ коммитить:**
- `.env` (реальные ключи)
- `data/` (база SQLite с логами)
- `*.tar.gz`, архивы деплоя
- `deploy_*.sh` (временные скрипты)

---

## Проверка перед пушем (чеклист)

- [ ] `git status` — нет `.env` в списке
- [ ] `git grep -i "sk-" -- "*.py"` — ничего не найдено
- [ ] `git grep -i "token.*=" -- "*.py"` — только примеры, не реальные ключи
- [ ] `.env.example` — пустые значения, только комментарии
- [ ] `README.md` — нет реальных IP/паролей/ключей

---

## Безопасность после публикации

Если репозиторий **публичный**:
- Любой может прочитать код (это нормально)
- Но НЕ должно быть ключей, IP-адресов сервера, паролей
- Все секреты — только в `.env` на сервере

Если репозиторий **приватный** (рекомендуется для такого проекта):
- Всё равно не коммить `.env` — привычка безопасности
- Можно указать IP сервера в `README.md` (но лучше не надо)

---

## Итог

**Команды для заливки:**

```bash
# 1. Проверка
git ls-files | grep "^\.env$"  # должно быть пусто

# 2. Коммит
git add -A
git commit -m "Description"

# 3. Push
git push origin master
```

**После публикации:**
- Проверь на GitHub, что `.env` не виден
- Если засветил ключи — перевыпусти их немедленно
