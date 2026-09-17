// --- Language dictionaries ---
const LABELS = {
    date:         { en: 'Date of transaction', hi: 'लेनदेन की तिथि' },
    amount:       { en: 'Income or expense amount', hi: 'आय या खर्च राशि' },
    type:         { en: 'Type', hi: 'प्रकार' },
    income:       { en: 'Income', hi: 'आमदनी' },
    expense:      { en: 'Expense', hi: 'खर्च' },
    category:     { en: 'Category', hi: 'श्रेणी' },
    food:         { en: 'Food', hi: 'भोजन' },
    utilities:    { en: 'Utilities', hi: 'यूटिलिटी' },
    farming:      { en: 'Farming', hi: 'कृषि' },
    medical:      { en: 'Medical', hi: 'चिकित्सा' },
    education:    { en: 'Education', hi: 'शिक्षा' },
    mode:         { en: 'Mode of Payment', hi: 'भुगतान का तरीका' },
    cash:         { en: 'Cash', hi: 'नकद' },
    upi:          { en: 'UPI', hi: 'यूपीआई' },
    bank:         { en: 'Bank', hi: 'बैंक' },
    notes:        { en: 'Notes', hi: 'विवरण' },
    notes_ph:     { en: 'Description (optional)', hi: 'विवरण (वैकल्पिक)' },
    addMore:      { en: 'Add More', hi: 'और जोड़ें' }
};

function getLabel(key) {
    if (typeof lang !== "undefined" && lang === 'hi') {
        return LABELS[key] && LABELS[key].hi ? LABELS[key].hi : LABELS[key].en;
    }
    return LABELS[key] ? LABELS[key].en : key;
}

// ------- Transactions -------
let transIdx = 0;
function addTransactionRow() {
    const tList = document.getElementById('transactions-list');
    const div = document.createElement('div');
    div.className = "grid grid-cols-1 md:grid-cols-7 gap-2 mb-2";

    div.innerHTML = `
      <div class="flex flex-col">
        <label class="mb-1 text-sm font-semibold">${getLabel('date')}</label>
        <input name="transactions-${transIdx}-date" type="date" class="border px-2 py-1" required>
      </div>
      <div class="flex flex-col">
        <label class="mb-1 text-sm font-semibold">${getLabel('amount')}</label>
        <input name="transactions-${transIdx}-amount" type="number" step="0.01" class="border px-2 py-1" placeholder="${getLabel('amount')}" required>
      </div>
      <div class="flex flex-col">
        <label class="mb-1 text-sm font-semibold">${getLabel('type')}</label>
        <select name="transactions-${transIdx}-type" class="border px-2 py-1" required>
          <option value="">${getLabel('type')}</option>
          <option value="Income">${getLabel('income')}</option>
          <option value="Expense">${getLabel('expense')}</option>
        </select>
      </div>
      <div class="flex flex-col">
        <label class="mb-1 text-sm font-semibold">${getLabel('category')}</label>
        <select name="transactions-${transIdx}-category" class="border px-2 py-1" required>
          <option value="">${getLabel('category')}</option>
          <option value="Food">${getLabel('food')}</option>
          <option value="Utilities">${getLabel('utilities')}</option>
          <option value="Farming">${getLabel('farming')}</option>
          <option value="Medical">${getLabel('medical')}</option>
          <option value="Education">${getLabel('education')}</option>
        </select>
      </div>
      <div class="flex flex-col">
        <label class="mb-1 text-sm font-semibold">${getLabel('mode')}</label>
        <select name="transactions-${transIdx}-mode_of_payment" class="border px-2 py-1" required>
          <option value="">${getLabel('mode')}</option>
          <option value="Cash">${getLabel('cash')}</option>
          <option value="UPI">${getLabel('upi')}</option>
          <option value="Bank">${getLabel('bank')}</option>
        </select>
      </div>
      <div class="flex flex-col col-span-2">
        <label class="mb-1 text-sm font-semibold">${getLabel('notes')}</label>
        <input name="transactions-${transIdx}-notes" class="border px-2 py-1" placeholder="${getLabel('notes_ph')}">
      </div>
      <div class="flex items-center justify-center">
        <button type="button" onclick="removeTransactionRow(this)" class="text-red-600 font-bold px-2 py-1">X</button>
      </div>
    `;
    tList.appendChild(div);
    transIdx++;
}
function removeTransactionRow(button) {
    // Remove the parent .grid div representing the row
    button.closest('div.grid').remove();
}
addTransactionRow(); // Initial row

// --------- Goals (if on same or related page) -------
const GOAL_LABELS = {
    goalName: { en: "Goal Name", hi: "लक्ष्य नाम" },
    targetAmount: { en: "Target Amount", hi: "लक्ष्य राशि" },
    savedAmount: { en: "Saved Amount", hi: "संचित राशि" },
    startDate: { en: "Start Date", hi: "प्रारंभ तिथि" },
    deadline: { en: "Deadline", hi: "समाप्ति तिथि" },
    goalType: { en: "Type", hi: "प्रकार" },
    priority: { en: "Priority", hi: "प्राथमिकता" },
    shortTerm: { en: "Short-term", hi: "लघु-मियादी" },
    longTerm: { en: "Long-term", hi: "दीर्घ-मियादी" },
    high: { en: "High", hi: "उच्च" },
    medium: { en: "Medium", hi: "मध्यम" },
    low: { en: "Low", hi: "निम्न" }
};

function getGoalLabel(key) {
    if (typeof lang !== "undefined" && lang === 'hi') {
        return GOAL_LABELS[key] && GOAL_LABELS[key].hi ? GOAL_LABELS[key].hi : GOAL_LABELS[key].en;
    }
    return GOAL_LABELS[key] ? GOAL_LABELS[key].en : key;
}

let goalIdx = 0;
function addGoalRow() {
    const gList = document.getElementById('goals-list');
    const div = document.createElement('div');
    div.className = "grid grid-cols-1 md:grid-cols-9 gap-2 mb-2";
    div.innerHTML = `
      <input name="goals-${goalIdx}-goal_name" class="border px-2 py-1" placeholder="${getGoalLabel('goalName')}" required>
      <input name="goals-${goalIdx}-target_amount" type="number" step="0.01" class="border px-2 py-1" placeholder="${getGoalLabel('targetAmount')}" required>
      <input name="goals-${goalIdx}-saved_amount" type="number" step="0.01" class="border px-2 py-1" placeholder="${getGoalLabel('savedAmount')}" required>
      <input name="goals-${goalIdx}-start_date" type="date" class="border px-2 py-1" required>
      <input name="goals-${goalIdx}-deadline" type="date" class="border px-2 py-1" required>
      <select name="goals-${goalIdx}-goal_type" class="border px-2 py-1" required>
        <option value="">${getGoalLabel('goalType')}</option>
        <option value="Short-term">${getGoalLabel('shortTerm')}</option>
        <option value="Long-term">${getGoalLabel('longTerm')}</option>
      </select>
      <select name="goals-${goalIdx}-priority" class="border px-2 py-1" required>
        <option value="">${getGoalLabel('priority')}</option>
        <option value="High">${getGoalLabel('high')}</option>
        <option value="Medium">${getGoalLabel('medium')}</option>
        <option value="Low">${getGoalLabel('low')}</option>
      </select>
      <button type="button" onclick="removeGoalRow(this)" class="text-red-600 font-bold px-2 py-1">X</button>
    `;
    gList.appendChild(div);
    goalIdx++;
}
function removeGoalRow(button) {
    button.parentNode.remove();
}
addGoalRow(); // Initial goal row
