const display = document.getElementById('display');
const buttons = document.querySelectorAll('.btn');

let currentValue = '0';
let previousValue = '';
let operator = null;
let shouldResetDisplay = false;

function updateDisplay() {
    display.textContent = currentValue;
}

function inputNumber(value) {
    if (shouldResetDisplay) {
        currentValue = value;
        shouldResetDisplay = false;
    } else {
        currentValue = currentValue === '0' ? value : currentValue + value;
    }
    updateDisplay();
}

function inputDecimal() {
    if (shouldResetDisplay) {
        currentValue = '0.';
        shouldResetDisplay = false;
        updateDisplay();
        return;
    }
    if (!currentValue.includes('.')) {
        currentValue += '.';
        updateDisplay();
    }
}

function handleOperator(nextOperator) {
    const current = parseFloat(currentValue);

    if (operator && !shouldResetDisplay) {
        const previous = parseFloat(previousValue);
        let result;

        switch (operator) {
            case '+': result = previous + current; break;
            case '-': result = previous - current; break;
            case '*': result = previous * current; break;
            case '/': result = current !== 0 ? previous / current : 'Error'; break;
        }

        currentValue = result === 'Error' ? 'Error' : String(result);
        updateDisplay();
    }

    previousValue = currentValue;
    operator = nextOperator;
    shouldResetDisplay = true;
}

function handleEquals() {
    if (!operator || shouldResetDisplay) return;
    handleOperator(null);
    operator = null;
}

function clear() {
    currentValue = '0';
    previousValue = '';
    operator = null;
    shouldResetDisplay = false;
    updateDisplay();
}

function toggleSign() {
    currentValue = String(parseFloat(currentValue) * -1);
    updateDisplay();
}

function handlePercent() {
    currentValue = String(parseFloat(currentValue) / 100);
    updateDisplay();
}

buttons.forEach(button => {
    button.addEventListener('click', () => {
        const action = button.dataset.action;
        const value = button.dataset.value;

        switch (action) {
            case 'number': inputNumber(value); break;
            case 'decimal': inputDecimal(); break;
            case 'operator': handleOperator(value); break;
            case 'equals': handleEquals(); break;
            case 'clear': clear(); break;
            case 'toggle-sign': toggleSign(); break;
            case 'percent': handlePercent(); break;
        }
    });
});

document.addEventListener('keydown', (e) => {
    if (e.key >= '0' && e.key <= '9') inputNumber(e.key);
    else if (e.key === '.') inputDecimal();
    else if (e.key === '+' || e.key === '-' || e.key === '*' || e.key === '/') handleOperator(e.key);
    else if (e.key === 'Enter' || e.key === '=') handleEquals();
    else if (e.key === 'Escape') clear();
    else if (e.key === '%') handlePercent();
});
