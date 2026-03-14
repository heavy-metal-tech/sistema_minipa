<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Minipa Precision | Registro de Entrada</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --minipa-blue: #0d47a1;
            --minipa-red: #d32f2f;
            --dark-blue: #061a33;
        }

        body { 
            background-color: #f0f2f5; 
            font-family: 'Inter', sans-serif;
            color: #2c3e50;
        }

        /* Navbar Sincronizada */
        .navbar { 
            background: white; 
            border-bottom: 4px solid var(--minipa-blue);
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .navbar-brand img { height: 50px; }

        /* Card de Registro */
        .card-os {
            background: white;
            border: none;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .os-header {
            background: linear-gradient(135deg, var(--dark-blue), var(--minipa-blue));
            color: white;
            padding: 25px;
            text-align: center;
        }

        .form-label {
            font-weight: 700;
            font-size: 0.85rem;
            color: var(--dark-blue);
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .form-control {
            border-radius: 10px;
            padding: 12px;
            border: 2px solid #eef2f7;
            background: #f8f9fa;
            transition: 0.3s;
        }

        .form-control:focus {
            border-color: var(--minipa-blue);
            background: white;
            box-shadow: 0 0 0 4px rgba(13, 71, 161, 0.1);
        }

        /* Tique de Garantia Customizado */
        .garantia-selector {
            display: flex;
            gap: 15px;
        }

        .garantia-option {
            flex: 1;
            position: relative;
        }

        .garantia-option input {
            position: absolute;
            opacity: 0;
            cursor: pointer;
        }

        .garantia-btn {
            display: block;
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border: 2px solid #eef2f7;
            border-radius: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.3s;
        }

        .garantia-option input:checked + .garantia-btn {
            background: var(--minipa-blue);
            color: white;
            border-color: var(--minipa-blue);
        }

        .btn-finalizar {
            background: var(--minipa-red);
            color: white;
            border: none;
            padding: 15px;
            border-radius: 12px;
            font-weight: 800;
            width: 100%;
            transition: 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .btn-finalizar:hover {
            background: #b71c1c;
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(211, 47, 47, 0.3);
        }
    </style>
</head>
<body>

<nav class="navbar mb-5">
    <div class="container d-flex justify-content-center">
        <a class="navbar-brand" href="{{ url_for('dashboard') }}">
            <img src="{{ url_for('static', filename='logo.png') }}">
        </a>
    </div>
</nav>

<div class="container pb-5">
    <div class="row justify-content-center">
        <div class="col-lg-8">
            <div class="card-os">
                <div class="os-header">
                    <h4 class="mb-0 fw-bold"><i class="fas fa-file-signature me-2"></i>Nova Ordem de Serviço</h4>
                    <small class="opacity-75">Unidade de Manutenção e Calibração</small>
                </div>
                
                <div class="card-body p-4 p-md-5">
                    <form action="{{ url_for('nova_os') }}" method="POST">
                        <div class="mb-4">
                            <label class="form-label">Cliente / Razão Social</label>
                            <input type="text" name="cliente" class="form-control shadow-sm" placeholder="Nome completo do cliente" required>
                        </div>

                        <div class="row">
                            <div class="col-md-7 mb-4">
                                <label class="form-label">Equipamento</label>
                                <input type="text" name="equipamento" class="form-control shadow-sm" placeholder="Ex: Multímetro ET-2042E" required>
                            </div>
                            <div class="col-md-5 mb-4">
                                <label class="form-label">Número de Série</label>
                                <input type="text" name="serie" class="form-control shadow-sm" placeholder="S/N" required>
                            </div>
                        </div>

                        <div class="row">
                            <div class="col-md-6 mb-4">
                                <label class="form-label">Status da Garantia</label>
                                <div class="garantia-selector">
                                    <label class="garantia-option">
                                        <input type="radio" name="garantia" value="Não" checked>
                                        <span class="garantia-btn"><i class="fas fa-times-circle me-1"></i> Fora</span>
                                    </label>
                                    <label class="garantia-option">
                                        <input type="radio" name="garantia" value="Sim">
                                        <span class="garantia-btn"><i class="fas fa-check-circle me-1"></i> Em Garantia</span>
                                    </label>
                                </div>
                            </div>
                            <div class="col-md-6 mb-4">
                                <label class="form-label">Valor Estimado (R$)</label>
                                <input type="text" name="valor" class="form-control shadow-sm" placeholder="0,00">
                            </div>
                        </div>

                        <div class="mb-5">
                            <label class="form-label">Descrição do Defeito</label>
                            <textarea name="defeito" class="form-control shadow-sm" rows="4" placeholder="Descreva os problemas relatados..."></textarea>
                        </div>

                        <div class="row g-3">
                            <div class="col-md-4">
                                <a href="{{ url_for('dashboard') }}" class="btn btn-light w-100 py-3 fw-bold text-muted rounded-pill">CANCELAR</a>
                            </div>
                            <div class="col-md-8">
                                <button type="submit" class="btn btn-finalizar shadow">GERAR ORDEM DE SERVIÇO</button>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
            <div class="text-center mt-4">
                <p class="small text-muted">Registro realizado pelo técnico: <strong>{{ current_user.nome_completo }}</strong></p>
            </div>
        </div>
    </div>
</div>

</body>
</html>
