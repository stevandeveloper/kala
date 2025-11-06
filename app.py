
import os
from datetime import datetime
from math import ceil

from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, current_user, logout_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- Config ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-please")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///kala.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

COMISION_PCT = 0.40
RECARGO_TRANSF_TJ = 0.15  # +15%

# ---------- Models ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="empleada")  # 'admin' or 'empleada'

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    efectivo = db.Column(db.Integer, nullable=False)  # precio base en efectivo (ARS)
    transf = db.Column(db.Integer, nullable=True)     # opcional (si no, se aplica +15%)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    efectivo = db.Column(db.Integer, nullable=False)
    transf = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, default=0)

class ServiceSale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    client_name = db.Column(db.String(200), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("service.id"), nullable=False)
    medio = db.Column(db.String(20), nullable=False)  # Efectivo, Transferencia, Tarjeta
    price_charged = db.Column(db.Integer, nullable=False)  # lo que se cobró a la clienta
    commission_base = db.Column(db.Integer, nullable=False) # base para comision (siempre efectivo)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    service = db.relationship("Service")
    user = db.relationship("User")

class ProductSale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    medio = db.Column(db.String(20), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    price_charged = db.Column(db.Integer, nullable=False)
    commission_base = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    product = db.relationship("Product")
    user = db.relationship("User")

# ---------- Auth ----------
@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# ---------- Helpers ----------
def ar(n):
    return f"${n:,.0f}".replace(",", ".")

def price_for_medium(efectivo, transf, medio):
    if medio == "Efectivo":
        return efectivo
    return transf if transf is not None else ceil(efectivo * (1 + RECARGO_TRANSF_TJ))

def commission_for_base(base_efectivo):
    return round(base_efectivo * COMISION_PCT)

# ---------- CLI init ----------
@app.cli.command("init")
def init_cmd():
    db.create_all()
    if not User.query.filter_by(email="admin@kala").first():
        admin = User(name="Stevan", email="admin@kala", role="admin")
        admin.set_password("kala123")
        db.session.add(admin)
        db.session.commit()
        print("✔ Admin creado: admin@kala / kala123")
    else:
        print("Admin ya existe")
    print("BD lista.")

# ---------- Routes ----------
@app.route("/")
@login_required
def home():
    # Totales para quien mira
    if current_user.role == "admin":
        svc = ServiceSale.query.order_by(ServiceSale.id.desc()).limit(10).all()
        prd = ProductSale.query.order_by(ProductSale.id.desc()).limit(10).all()
        total = sum(s.price_charged for s in ServiceSale.query) + sum(p.price_charged for p in ProductSale.query)
        com_total = sum(commission_for_base(s.commission_base) for s in ServiceSale.query) + \
                    sum(commission_for_base(p.commission_base) for p in ProductSale.query)
    else:
        svc = ServiceSale.query.filter_by(user_id=current_user.id).order_by(ServiceSale.id.desc()).limit(10).all()
        prd = ProductSale.query.filter_by(user_id=current_user.id).order_by(ProductSale.id.desc()).limit(10).all()
        total = sum(s.price_charged for s in ServiceSale.query.filter_by(user_id=current_user.id)) + \
                sum(p.price_charged for p in ProductSale.query.filter_by(user_id=current_user.id))
        com_total = sum(commission_for_base(s.commission_base) for s in ServiceSale.query.filter_by(user_id=current_user.id)) + \
                    sum(commission_for_base(p.commission_base) for p in ProductSale.query.filter_by(user_id=current_user.id))

    return render_template("dashboard.html", svc=svc, prd=prd, total=total, com_total=com_total, ar=ar)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        pw = request.form["password"]
        u = User.query.filter_by(email=email).first()
        if u and u.check_password(pw):
            login_user(u)
            return redirect(url_for("home"))
        flash("Usuario o contraseña incorrectos", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ---------- Admin: Catálogo & Usuarios ----------
def ensure_admin():
    if current_user.role != "admin":
        flash("Solo admin.", "warning")
        return False
    return True

@app.route("/admin/catalogo", methods=["GET","POST"])
@login_required
def admin_catalog():
    if not ensure_admin(): return redirect(url_for("home"))
    if request.method == "POST":
        kind = request.form["kind"]
        name = request.form["name"].strip()
        efectivo = int(request.form["efectivo"] or 0)
        transf = request.form.get("transf", "").strip()
        transf_val = int(transf) if transf else None
        if kind == "service":
            db.session.add(Service(name=name, efectivo=efectivo, transf=transf_val))
        else:
            stock = int(request.form.get("stock") or 0)
            db.session.add(Product(name=name, efectivo=efectivo, transf=transf_val, stock=stock))
        db.session.commit()
        flash("Guardado", "success")
        return redirect(url_for("admin_catalog"))
    return render_template("catalog.html",
        services=Service.query.order_by(Service.name.asc()).all(),
        products=Product.query.order_by(Product.name.asc()).all()
    )

@app.route("/admin/usuarios", methods=["GET","POST"])
@login_required
def admin_users():
    if not ensure_admin(): return redirect(url_for("home"))
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        role = request.form["role"]
        pw = request.form["password"]
        u = User(name=name, email=email, role=role)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        flash("Usuario creado", "success")
        return redirect(url_for("admin_users"))
    return render_template("users.html", users=User.query.order_by(User.name.asc()).all())

# ---------- Registrar ventas ----------
@app.route("/venta/servicio", methods=["GET","POST"])
@login_required
def venta_servicio():
    services = Service.query.order_by(Service.name.asc()).all()
    if request.method == "POST":
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        client = request.form["client"]
        service_id = int(request.form["service_id"])
        medio = request.form["medio"]
        svc = Service.query.get(service_id)
        base = svc.efectivo
        charged = price_for_medium(svc.efectivo, svc.transf, medio)
        sale = ServiceSale(date=date, client_name=client, service_id=service_id,
                           medio=medio, price_charged=charged,
                           commission_base=base, user_id=current_user.id)
        db.session.add(sale)
        db.session.commit()
        flash("Venta de servicio cargada", "success")
        return redirect(url_for("home"))
    return render_template("venta_servicio.html", services=services, today=datetime.utcnow().strftime("%Y-%m-%d"))

@app.route("/venta/producto", methods=["GET","POST"])
@login_required
def venta_producto():
    products = Product.query.order_by(Product.name.asc()).all()
    if request.method == "POST":
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        product_id = int(request.form["product_id"])
        medio = request.form["medio"]
        qty = int(request.form["qty"] or 1)
        p = Product.query.get(product_id)
        unit_base = p.efectivo
        unit_charged = price_for_medium(p.efectivo, p.transf, medio)
        charged = unit_charged * qty
        sale = ProductSale(date=date, product_id=product_id, medio=medio, qty=qty,
                           price_charged=charged, commission_base=unit_base*qty,
                           user_id=current_user.id)
        # opcional: descontar stock si admin así lo setea
        p.stock = (p.stock or 0) - qty
        db.session.add(sale)
        db.session.commit()
        flash("Venta de producto cargada", "success")
        return redirect(url_for("home"))
    return render_template("venta_producto.html", products=products, today=datetime.utcnow().strftime("%Y-%m-%d"))

# ---------- Reportes ----------
@app.route("/mis-comisiones")
@login_required
def mis_comisiones():
    if current_user.role == "admin":
        sales_s = ServiceSale.query.all()
        sales_p = ProductSale.query.all()
    else:
        sales_s = ServiceSale.query.filter_by(user_id=current_user.id).all()
        sales_p = ProductSale.query.filter_by(user_id=current_user.id).all()
    total_base = sum(s.commission_base for s in sales_s) + sum(p.commission_base for p in sales_p)
    total_com = commission_for_base(total_base)
    total_fact = sum(s.price_charged for s in sales_s) + sum(p.price_charged for p in sales_p)
    return render_template("comisiones.html", total_base=total_base, total_com=total_com, total_fact=total_fact, ar=ar)

# ---------- Seed de catálogo (tu lista) ----------
@app.route("/admin/seed")
@login_required
def admin_seed():
    if not ensure_admin(): return redirect(url_for("home"))
    if Service.query.count() == 0:
        services = [
            ("Alisado (con formol)", 52500, 58500),
            ("Botox s/ formol", 49000, 54500),
            ("Shock de palta", 49000, 54500),
            ("Keratina c/ células madres", 45000, 50500),
            ("Alisado sin formol (brasileño)", 79500, 88500),
            ("Alineamiento capilar", 79500, 88500),
            ("SOS reconstructor", 79500, 88500),
            ("Diseño y perfilado de cejas", 9000, 10350),
            ("Diseño + perfilado + Henna", 11500, 13250),
            ("Laminado de cejas + diseño", 16500, 18950),
            ("Lifting de pestañas nutritivo + tinte", 17000, 19100),
            ("Sombreado con henna/tinte", 7000, 8050),
        ]
        for n, e, t in services:
            db.session.add(Service(name=n, efectivo=e, transf=t))
    if Product.query.count() == 0:
        products = [
            ("Protector térmico", 8500, int(8500*1.15), 0),
            ("Baño de crema Biotina", 6500, int(6500*1.15), 0),
            ("Shampoo neutro", 4800, int(4800*1.15), 0),
            ("Keratina líquida", 12000, int(12000*1.15), 0),
            ("Biotina líquida", 7500, int(7500*1.15), 0),
        ]
        for n, e, t, s in products:
            db.session.add(Product(name=n, efectivo=e, transf=t, stock=s))
    db.session.commit()
    flash("Catálogo cargado", "success")
    return redirect(url_for("admin_catalog"))

# ---------- Run ----------
# ---------- Setup (solo primera vez) ----------

from flask import Response
@app.route("/init")
def init_db_and_admin():
    """Crea tablas y un admin por única vez si no hay usuarios."""
    with app.app_context():
        db.create_all()
        if User.query.count() > 0:
            return Response("Ya hay usuarios creados. Nada que hacer.", mimetype="text/plain")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@kala")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "kala123")
        u = User(name="Admin", email=admin_email, role="admin")
        u.set_password(admin_pass)
        db.session.add(u)
        db.session.commit()
        return Response(f"✅ Admin creado: {admin_email} / {admin_pass}", mimetype="text/plain")

# ⚠️ Importante:
# Dejamos UNA SOLA seed: la que ya tenés más arriba (@app.route('/admin/seed') con login).
# Eliminamos la segunda seed que había cortada al final para evitar conflictos.

# ---------- Run local ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
