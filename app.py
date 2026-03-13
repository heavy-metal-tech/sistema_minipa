# --- TABELA DE ESTOQUE DE PEÇAS ---
class Estoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    minimo = db.Column(db.Integer, default=5) # Alerta quando o estoque estiver baixo

# Rota para ver o estoque (opcional para agora, mas bom ter)
@app.route('/estoque')
@login_required
def estoque():
    pecas = Estoque.query.all()
    return render_template('estoque.html', pecas=pecas)
