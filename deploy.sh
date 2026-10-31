#!/usr/bin/env bash
# BankNifty AI Bot — Oracle VM एक-क्लिक डिप्लॉय (मराठी)
set -e

echo "==============================================="
echo "  🤖 BankNifty AI Bot — डिप्लॉय सुरू"
echo "==============================================="

echo "▶ १/५: आवश्यक साधने इन्स्टॉल (1-2 मिनिटे)..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv python3-pip git iptables-persistent

echo "▶ २/५: बॉटचा कोड GitHub वरून उतरवत आहे..."
cd ~
rm -rf banknifty_bot
git clone -q https://github.com/amoltalekar84-stack/banknifty_bot.git
echo "   ✓ कोड तयार: ~/banknifty_bot"

echo "▶ ३/५: Python वातावरण + पॅकेजेस (येथे 2-4 मिनिटे लागतील, थांबा)..."
cd ~/banknifty_bot
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "   ✓ सर्व पॅकेजेस इन्स्टॉल!"

echo "▶ ४/५: 24/7 सेवा (systemd) तयार करत आहे..."
sudo tee /etc/systemd/system/banknifty.service > /dev/null <<'EOF'
[Unit]
Description=BankNifty AI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/banknifty_bot
ExecStart=/home/ubuntu/banknifty_bot/venv/bin/python app.py
Restart=always
RestartSec=10
Environment=DATA_DIR=/home/ubuntu/banknifty_bot/data
EnvironmentFile=-/home/ubuntu/banknifty_bot/bot.env

[Install]
WantedBy=multi-user.target
EOF

sudo iptables -I INPUT -p tcp --dport 7860 -j ACCEPT 2>/dev/null || true
sudo netfilter-persistent save > /dev/null 2>&1 || true

echo "▶ ५/५: बॉट सुरू करत आहे..."
sudo systemctl daemon-reload
sudo systemctl enable --now banknifty -q
sleep 6

echo "==============================================="
systemctl status banknifty --no-pager | head -12 || true
curl -s -o /dev/null -w "डॅशबोर्ड तपासणी: HTTP %{http_code}\n" http://localhost:7860 || echo "डॅशबोर्ड अजून उठतो आहे (30 सेकंद थांबवून पुन्हा चाचणी करा)"
echo "==============================================="
echo "✅ डिप्लॉय पूर्ण! ही स्क्रीन शेवटपर्यंत स्क्रीनशॉट करा."
