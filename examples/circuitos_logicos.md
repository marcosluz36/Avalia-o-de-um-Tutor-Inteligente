# Circuitos Lógicos - material de teste

Texto didático original criado para verificar o TutorIA. Este material não é uma
transcrição de livro, artigo ou aula. As regras abaixo usam lógica booleana binária.

## Teoremas de De Morgan

Notação: !A representa o complemento (negação) de A; o operador * representa AND;
o operador + representa OR. A e B são variáveis booleanas, com valores 0 ou 1.

O complemento de uma soma lógica é igual ao produto lógico dos complementos:
!(A + B) = !A * !B.

O complemento de um produto lógico é igual à soma lógica dos complementos:
!(A * B) = !A + !B.

Ao distribuir a negação sobre uma expressão, a operação AND é trocada por OR,
ou OR por AND, e cada operando é complementado. A negação externa deve abranger
toda a expressão indicada pelos parênteses.

Exemplo deste material: para A = 0 e B = 1, !(A+B) = !(0+1) = 0.
Pelo outro lado da igualdade, !A * !B = 1 * 0 = 0.

| A | B | !(A+B) | !A * !B |
|---|---|---|---|
| 0 | 0 | 1 | 1 |
| 0 | 1 | 0 | 0 |
| 1 | 0 | 0 | 0 |
| 1 | 1 | 0 | 0 |

## Circuitos combinacionais e sequenciais

Um circuito combinacional tem saídas determinadas pelas entradas atuais e não
armazena um estado interno para determinar essas saídas. Um circuito sequencial
armazena estado; suas saídas dependem do estado e, conforme o circuito, também
das entradas atuais.

Um latch D com habilitação ativa em nível alto permite que Q acompanhe D enquanto
a habilitação está em 1. Quando a habilitação está em 0, mantém o dado armazenado.
Um flip-flop D acionado na borda de subida amostra D na transição de 0 para 1 do
clock, respeitadas as condições de temporização, e mantém Q entre bordas ativas.
A diferença central é a sensibilidade a nível, no latch, e a borda, no flip-flop.

## Exercício e regras de apoio

Exercício: simplifique F = !(A + B) + !A * B.

Tentativa incorreta para discussão: F = !A + !B + !A * B.
É preciso conferir a aplicação da negação externa ao primeiro termo.

Regras disponíveis neste material:

- De Morgan: !(A + B) = !A * !B.
- Distributividade: X*Y + X*Z = X*(Y + Z).
- Complementaridade: !B + B = 1.
- Identidade: X * 1 = X.

Um caminho de resolução é substituir o primeiro termo por seu equivalente de
De Morgan, colocar o fator comum em evidência e aplicar complementaridade e
identidade. A solução final pode ser deduzida dessas regras.
