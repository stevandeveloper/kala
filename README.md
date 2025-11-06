# Kala — App web (Flask + SQLite)

Rol admin y empleadas, catálogo de **servicios** y **productos**, ventas con **+15%** transf/tarjeta, comisión **40%** sobre efectivo, reportes y control básico de stock.

## Uso local (opcional)
```bash
pip install -r requirements.txt
flask --app app.py init  # crea admin y BD
flask --app app.py run
```
Admin por defecto: **admin@kala / kala123** (cambiar luego).

## Deploy (sin instalar nada)
1. Subí esta carpeta a un **repo GitHub**.
2. En **render.com** → *New Web Service* → conecta el repo.
3. **Runtime**: Python 3.x  
   **Build Command**: `pip install -r requirements.txt`  
   **Start Command**: `gunicorn app:app`
4. Agregá **Environment Variables**:
   - `SECRET_KEY` (cualquier string largo)
   - `DATABASE_URL` (opcional; si omitís, usa SQLite)
5. Deploy y listo. Entrá a `/login`. Crea admin desde **Usuarios** o ejecutá el comando `init` si corrés local.

## Importante
- En **Catálogo** cargás precios en efectivo y (opcional) precio específico para transf/tarjeta; si lo dejás vacío, la app usa **+15% automático**.
- Las **empleadas** solo ven **sus ventas y sus comisiones**. El **admin** ve todo.
