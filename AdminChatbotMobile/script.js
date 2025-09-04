document.addEventListener('DOMContentLoaded', () => {
    const instructionsContainer = document.getElementById('instructions-container');
    const saveButton = document.getElementById('save-button');
    const apiUrl = 'https://chatbotmobile.quandoiai.vn/instructions';

    let originalInstructions = [];

    async function fetchInstructions() {
        instructionsContainer.innerHTML = '';
        instructionsContainer.classList.add('loading');
        try {
            // In a real scenario, you would use fetch:
            const response = await fetch(apiUrl);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            let data = await response.json();

            const sortOrder = [
                "base_instructions",
                "product_workflow",
                "service_workflow",
                "accessory_workflow",
                "workflow_instructions",
                "other_instructions"
            ];

            data.sort((a, b) => sortOrder.indexOf(a.key) - sortOrder.indexOf(b.key));

            originalInstructions = data;
            renderInstructions(data);
        } catch (error) {
            instructionsContainer.innerHTML = '<p style="color: red; text-align: center;">Failed to load instructions. Please try again later.</p>';
            console.error('Error fetching instructions:', error);
        } finally {
            instructionsContainer.classList.remove('loading');
        }
    }

    const keyToTitleMap = {
        "base_instructions": "Hướng dẫn cơ bản",
        "product_workflow": "Luồng xử lý sản phẩm",
        "service_workflow": "Luồng xử lý dịch vụ",
        "accessory_workflow": "Luồng xử lý linh kiện/phụ kiện",
        "workflow_instructions": "Hướng dẫn luồng xử lý",
        "other_instructions": "Các hướng dẫn khác"
    };

    function renderInstructions(instructions) {
        instructionsContainer.innerHTML = '';
        instructions.forEach(instruction => {
            const card = document.createElement('div');
            card.className = 'instruction-card';
            card.dataset.key = instruction.key;

            const header = document.createElement('div');
            header.className = 'instruction-header';
            
            const title = document.createElement('h2');
            title.textContent = keyToTitleMap[instruction.key] || instruction.key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            header.appendChild(title);

            const body = document.createElement('div');
            body.className = 'instruction-body';

            const textarea = document.createElement('textarea');
            textarea.value = instruction.value.trim();
            body.appendChild(textarea);
            
            card.appendChild(header);
            card.appendChild(body);
            instructionsContainer.appendChild(card);
        });
    }

    async function saveInstructions() {
        const updatedInstructions = [];
        const cards = document.querySelectorAll('.instruction-card');
        
        cards.forEach(card => {
            const key = card.dataset.key;
            const value = card.querySelector('textarea').value;
            updatedInstructions.push({ key, value });
        });

        const payload = {
            instructions: updatedInstructions
        };

        saveButton.textContent = 'Đang lưu...';
        saveButton.disabled = true;

        try {
            // In a real scenario, you would use fetch:
            const response = await fetch(apiUrl, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            // Simulating API call
            // await new Promise(resolve => setTimeout(resolve, 1000));
            console.log('Data sent to server:', JSON.stringify(payload, null, 2));

            alert('Instructions saved successfully!');
            originalInstructions = updatedInstructions; // Update original state
        } catch (error) {
            alert('Failed to save instructions. Please check the console for details.');
            console.error('Error saving instructions:', error);
        } finally {
            saveButton.textContent = 'Lưu thay đổi';
            saveButton.disabled = false;
        }
    }

    saveButton.addEventListener('click', saveInstructions);

    fetchInstructions();
});
