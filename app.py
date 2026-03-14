<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Minipa Precision | Command Center</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --minipa-blue: #0d47a1;
            --dark-bg: #061a33;
            --accent-cyan: #00e5ff;
            --glass: rgba(255, 255, 255, 0.95);
        }

        body { 
            background-color: #f0f2f5; 
            font-family: 'Inter', sans-serif;
            color: #2c3e50;
        }

        /* Navbar de Impacto */
        .navbar { 
            background: white; 
            border-bottom: 4px solid var(--minipa-blue);
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .navbar-brand img { height: 55px; }

        /* Dashboard Cards */
        .card-stats {
            background: linear-gradient(135deg, var(--dark-bg), var(--minipa-blue));
            color: white;
            border: none;
            border-radius: 15px;
            transition: 0.3s;
        }
        .card-stats:hover { transform: translateY(-5px); }

        .card-white {
            background: white;
            border: none;
            border-radius: 15px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.05);
        }

        /* Gráficos */
        .chart-container { position: relative; height: 250px; width: 100%; }

        /* Tabela Estilizada */
        .table thead { background: var(--dark-bg); color: white; }
        .os-row:hover { background: #f8f9fa !important; }

        /* Botão Pulsante */
        .btn-new {
            background: #d32f2f;
            border: none;
            border-radius: 50px;
            font-weight: 800;
            padding: 12px 30px;
            box-shadow: 0 4px 15px rgba(211, 47, 47, 0.4);
        }
        .btn-new:hover { background: #b71c1c; transform: scale(1.05); color: white; }
    </style>
</head>
<body>

<nav class="navbar mb-4 py-2">
    <div class="container d-flex justify-content-between align-items-center">
        <a class="navbar-brand" href="#"><img src="{{ url_for('static', filename='logo.png') }}"></a>
        <div class="d-flex gap-2">
            <a href="{{ url_for('pdf_estoque') }}" class="btn btn-dark btn-sm rounded-pill px-3">
                <i class="fas fa-file-invoice me-2"></i>Relatório Geral
            </a>
            <div class="bg-primary text-white px-3 py-1 rounded-pill small d-flex align-items-center">
                <i class="fas fa-user-circle me-2"></i> {{ current_user.nome_completo }}
            </div>
            <a href="{{ url_for('logout') }}" class="btn btn-outline-danger btn-sm rounded-circle"><i class="fas fa-power-off"></i></a>
        </div>
    </div>
</nav>

<div class="container pb-5">
    <div class="row g-4 mb-5">
        <div class="col-md-3">
            <div class="card-stats p-4 h-100 d-flex flex-column justify-content-center">
                <small class="opacity-75">Serviços Ativos</small>
                <h1 class="display-4 fw-bold mb-0">{{ ordens|length }}</h1>
                <div class="mt-3"><i class="fas fa-microchip fa-2x opacity-25"></i></div>
            </div>
        </div>
        <div class="col-md-5">
            <div class="card-white p-4 h-100">
                <h6 class="fw-bold mb-3"><i class="fas fa-chart-line text-primary me-2"></i>Volume de Atendimento</h6>
                <div class="chart-container">
                    <canvas id="mainChart"></canvas>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card-white p-4 h-100 text-center">
                <h6 class="fw-bold mb-4">Ações Rápidas</h6>
                <a href="{{ url_for('nova_os') }}" class="btn btn-new mb-3 w-100">
                    <i class="fas fa-plus-circle me-2"></i>ABRIR NOVA OS
                </a>
                <div class="alert alert-info py-2 small border-0">
                    <i class="fas fa-info-circle me-2"></i> {{ estoque|length }} itens em estoque.
                </div>
            </div>
        </div>
    </div>

    <div class="card-white overflow-hidden mb-5">
        <div class="p-3 bg-light border-bottom d-flex justify-content-between">
            <span class="fw-bold text-dark"><i class="fas fa-list me-2"></i>Fila de Reparo</span>
            <span class="text-muted small">Atualizado em tempo real</span>
        </div>
        <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
                <thead>
                    <tr>
                        <th class="ps-4">OS</th>
                        <th>Cliente</th>
                        <th>Equipamento</th>
                        <th>Valor Estimado</th>
                        <th class="text-center">Ação</th>
                    </tr>
                </thead>
                <tbody>
                    {% for os in ordens %}
                    <tr class="os-row">
                        <td class="ps-4 fw-bold text-primary">#{{ os.id }}</td>
                        <td><div class="fw-bold">{{ os.cliente }}</div><small class="text-muted">{{ os.serie }}</small></td>
                        <td><span class="badge bg-light text-primary border border-primary-subtle">{{ os.equipamento }}</span></td>
                        <td class="fw-bold">R$ {{ os.valor }}</td>
                        <td class="text-center">
                            <a href="{{ url_for('pdf_os', id=os.id) }}" class="btn btn-sm btn-outline-danger px-3 rounded-pill">
                                <i class="fas fa-file-pdf"></i> PDF
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div class="row g-4">
        <div class="col-md-7">
            <div class="card-white p-0 overflow-hidden">
                <div class="p-3 bg-dark text-white fw-bold"><i class="fas fa-warehouse me-2"></i>Inventário Crítico</div>
                <table class="table table-sm mb-0">
                    <thead class="table-light">
                        <tr><th class="ps-3">Item</th><th>Qtd</th><th>Posição</th></tr>
                    </thead>
                    <tbody>
                        {% for item in estoque %}
                        <tr><td class="ps-3">{{ item.componente }}</td><td><span class="badge bg-secondary">{{ item.quantidade }}</span></td><td>{{ item.posicao }}</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        {% if current_user.is_admin %}
        <div class="col-md-5">
            <div class="card-white p-4 border-start border-primary border-5">
                <h6 class="fw-bold mb-3">Gerenciamento de Técnicos</h6>
                <form action="{{ url_for('novo_tecnico') }}" method="POST">
                    <div class="mb-2"><input type="text" name="nome" class="form-control form-control-sm" placeholder="Nome Completo" required></div>
                    <div class="mb-2"><input type="text" name="username" class="form-control form-control-sm" placeholder="Login" required></div>
                    <div class="mb-2"><input type="password" name="password" class="form-control form-control-sm" placeholder="Senha" required></div>
                    <button type="submit" class="btn btn-primary btn-sm w-100">Cadastrar Novo Acesso</button>
                </form>
            </div>
        </div>
        {% endif %}
    </div>
</div>

<script>
    // Lógica do Gráfico de Volume
    const ctx = document.getElementById('mainChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex'],
            datasets: [{
                label: 'OS Abertas',
                data: [5, 8, {{ ordens|length }}, 10, 15],
                borderColor: '#0d47a1',
                backgroundColor: 'rgba(13, 71, 161, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
</script>

</body>
</html>
