#!/usr/bin/env ruby
# Programma di prova per il debugger MCP: qualche funzione, un loop e
# un bug voluto (sconto applicato due volte) da scovare col debugger.

Prodotto = Struct.new(:nome, :prezzo, :quantita)

def carrello
  [
    Prodotto.new("tastiera", 45.0, 1),
    Prodotto.new("mouse", 25.0, 2),
    Prodotto.new("monitor", 180.0, 1)
  ]
end

def applica_sconto(prezzo, percentuale)
  prezzo - (prezzo * percentuale / 100.0)
end

def totale_carrello(prodotti, sconto: 10)
  totale = 0.0
  prodotti.each do |p|
    parziale = applica_sconto(p.prezzo, sconto) * p.quantita
    # BUG voluto: lo sconto viene applicato una seconda volta sul parziale
    totale += applica_sconto(parziale, sconto)
  end
  totale.round(2)
end

prodotti = carrello
totale = totale_carrello(prodotti)
puts "Prodotti: #{prodotti.size}"
puts "Totale scontato: #{totale} EUR"
puts "Atteso (sconto 10% singolo): 247.50 EUR"
