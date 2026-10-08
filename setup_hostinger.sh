#!/bin/bash
# ==============================================================================
# 🧠 AGENT BRAIN | AUTONOMOUS 24/7 DEPLOYMENT SCRIPT (ALMALINUX 9 / CYBERPANEL)
# Target Host: 62.72.31.29 (Hostinger KVM 2)
# ==============================================================================

set -e

echo "=================================================================="
echo "  🧠 AGENT BRAIN 24/7 DEPLOYMENT - ALMALINUX 9 / HOSTINGER KVM 2  "
echo "=================================================================="

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📍 Application Directory: $APP_DIR"

# 1. Update package manager & install python3 / pip
echo "📦 Step 1: Checking and installing Python 3 dependencies..."
dnf install -y python3 python3-pip gcc 2>/dev/null || true

# 2. Set up Python Virtual Environment
echo "🐍 Step 2: Setting up isolated Python virtual environment (.venv)..."
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi

"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 3. Check for .env file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️ Warning: .env file not found. Copying .env.example to .env..."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "⚡ Please verify your DELTA_API_KEY and DELTA_API_SECRET in $APP_DIR/.env"
fi

# 4. Create Systemd Service for Live Trader Engine (run_live_trader.py)
echo "⚙️ Step 3: Installing 24/7 systemd service for Live Trader Engine..."
cat << EOF > /etc/systemd/system/trading-brain.service
[Unit]
Description=Agent Brain - Autonomous Multi-Pair Live Trader Engine
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/run_live_trader.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 5. Create Systemd Service for Live Dashboard Server (server.py)
echo "⚙️ Step 4: Installing 24/7 systemd service for Live Web Dashboard..."
cat << EOF > /etc/systemd/system/trading-dashboard.service
[Unit]
Description=Agent Brain - Interactive Web Dashboard & Command Cockpit
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=DASHBOARD_HOST=0.0.0.0

[Install]
WantedBy=multi-user.target
EOF

# 6. Create Systemd Service for 24/7 L2 DOM Recorder (scripts/record_l2_dom.py)
echo "⚙️ Step 5: Installing 24/7 systemd service for Level 2 DOM Recorder..."
cat << EOF > /etc/systemd/system/trading-dom-recorder.service
[Unit]
Description=Agent Brain - 24/7 Level 2 DOM Orderbook & Heatmap Recorder
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/scripts/record_l2_dom.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 7. Reload Systemd & Start Services
echo "🚀 Step 6: Enabling and starting background services..."
systemctl daemon-reload
systemctl enable trading-brain.service
systemctl enable trading-dashboard.service
systemctl enable trading-dom-recorder.service
systemctl restart trading-brain.service
systemctl restart trading-dashboard.service
systemctl restart trading-dom-recorder.service

# 7. Open Firewall Port 5050 for Live Journal Dashboard
echo "🛡️ Step 6: Configuring firewall rules for port 5050..."
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=5050/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

# If CSF firewall is used by CyberPanel
if [ -f /etc/csf/csf.conf ]; then
    if ! grep -q "5050" /etc/csf/csf.conf; then
        sed -i 's/TCP_IN = "/TCP_IN = "5050,/g' /etc/csf/csf.conf
        csf -r 2>/dev/null || true
    fi
fi

echo ""
echo "=================================================================="
echo "  ✅ AGENT BRAIN SUCCESSFULLY DEPLOYED AND RUNNING 24/7!          "
echo "=================================================================="
echo "  📊 Live Journal Cockpit:  http://62.72.31.29:5050"
echo "  📈 L2 DOM Heatmap:        http://62.72.31.29:5050/dom_heatmap.html"
echo "  🤖 Check Engine Status:   systemctl status trading-brain"
echo "  📋 View Live Engine Logs: journalctl -u trading-brain -f"
echo "  📊 Check DOM Recorder:    systemctl status trading-dom-recorder"
echo "  📜 View DOM Recorder Logs:journalctl -u trading-dom-recorder -f"
echo "  🌐 Check Dashboard Status:systemctl status trading-dashboard"
echo "=================================================================="
