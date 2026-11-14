// SHOW PAGES
function showPage(pageId) {
    const pages = ["add", "view", "borrow", "return"];

    pages.forEach(id => {
        document.getElementById(id).style.display = "none";
    });

    document.getElementById(pageId).style.display = "block";
}


// GO BACK TO DASHBOARD
function goHome() {
    const pages = ["add", "view", "borrow", "return"];

    pages.forEach(id => {
        document.getElementById(id).style.display = "none";
    });

    loadDashboardStats();
}


// ADD BOOK
async function addBook() {
    const id = document.getElementById("bookId").value.trim();
    const name = document.getElementById("bookName").value.trim();
    const author = document.getElementById("author").value.trim();

    if (!id || !name || !author) {
        alert("Please fill all details!");
        return;
    }

    try {
        const response = await fetch("/api/books", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ id, name, author })
        });

        const data = await response.json();

        alert(data.message);

        if (response.ok) {
            document.getElementById("bookId").value = "";
            document.getElementById("bookName").value = "";
            document.getElementById("author").value = "";

            goHome();
        }

    } catch (error) {
        alert("Unable to connect to server!");
        console.error(error);
    }
}


// VIEW BOOKS
async function viewBooks() {
    showPage("view");

    const output = document.getElementById("bookList");
    output.innerHTML = "Loading books...";

    document.getElementById("searchResult").innerHTML = "";

    try {
        const response = await fetch("/api/books");
        const books = await response.json();

        if (!response.ok) {
            throw new Error("Unable to load books");
        }

        if (books.length === 0) {
            output.innerHTML = "<p>No books available.</p>";
            return;
        }

        output.innerHTML = books.map(book => `
            <div class="book-item">
                <h3>${escapeHTML(book.name)}</h3>
                <p>Book ID: ${escapeHTML(book.id)}</p>
                <p>Author: ${escapeHTML(book.author)}</p>
                <p>Status: ${escapeHTML(book.status)}</p>
            </div>
        `).join("");

    } catch (error) {
        output.innerHTML = "<p>Unable to load books.</p>";
        console.error(error);
    }
}


// BORROW BOOK
async function borrowBook() {
    const id = document.getElementById("borrowId").value.trim();

    if (!id) {
        alert("Please enter Book ID!");
        return;
    }

    try {
        const response = await fetch(
            `/api/books/${encodeURIComponent(id)}/borrow`,
            {
                method: "POST"
            }
        );

        const data = await response.json();

        alert(data.message);

        if (response.ok) {
            document.getElementById("borrowId").value = "";
            goHome();
        }

    } catch (error) {
        alert("Unable to connect to server!");
        console.error(error);
    }
}


// RETURN BOOK
async function returnBook() {
    const id = document.getElementById("returnId").value.trim();

    if (!id) {
        alert("Please enter Book ID!");
        return;
    }

    try {
        const response = await fetch(
            `/api/books/${encodeURIComponent(id)}/return`,
            {
                method: "POST"
            }
        );

        const data = await response.json();

        alert(data.message);

        if (response.ok) {
            document.getElementById("returnId").value = "";
            goHome();
        }

    } catch (error) {
        alert("Unable to connect to server!");
        console.error(error);
    }
}


// SEARCH BOOK
async function searchBook() {
    const input = document.getElementById("searchName");
    const output = document.getElementById("searchResult");

    const name = input.value.trim();

    if (!name) {
        output.innerHTML = "<p>Please enter a book name.</p>";
        return;
    }

    try {
        const response = await fetch(
            "/api/books/search?q=" + encodeURIComponent(name)
        );

        const books = await response.json();

        if (!response.ok) {
            throw new Error("Search failed");
        }

        if (books.length === 0) {
            output.innerHTML = "<p>Book not found!</p>";
            return;
        }

        output.innerHTML = books.map(book => `
            <div class="book-item">
                <h3>${escapeHTML(book.name)}</h3>
                <p>Book ID: ${escapeHTML(book.id)}</p>
                <p>Author: ${escapeHTML(book.author)}</p>
                <p>Status: ${escapeHTML(book.status)}</p>
            </div>
        `).join("");

    } catch (error) {
        output.innerHTML = "<p>Search failed!</p>";
        console.error(error);
    }
}


// ESCAPE HTML
function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}


// LOAD DASHBOARD STATISTICS
async function loadDashboardStats() {
    try {
        const response = await fetch("/api/stats");

        if (!response.ok) {
            throw new Error("Unable to load statistics");
        }

        const stats = await response.json();

        document.getElementById("totalBooks").textContent = stats.total;
        document.getElementById("availableBooks").textContent = stats.available;
        document.getElementById("borrowedBooks").textContent = stats.borrowed;

    } catch (error) {
        console.error("Statistics error:", error);
    }
}


// LOAD STATISTICS WHEN PAGE OPENS
document.addEventListener("DOMContentLoaded", function () {
    loadDashboardStats();
    loadActivity();
    loadBookChart();
});
async function loadActivity() {
    const activityList = document.getElementById("activityList");

    if (!activityList) return;

    try {
        const response = await fetch("/api/activity");

        if (!response.ok) {
            throw new Error("Could not load activities");
        }

              const activities = await response.json();
              

        if (activities.length === 0) {
            activityList.innerHTML = "<p>No recent activity.</p>";
            return;
        }

        activityList.innerHTML = activities.map(item => `
            <div class="activity-item">
                <strong>${escapeHTML(item.action)}</strong>
                — ${escapeHTML(item.book_name)}
                <br>
                <small>${escapeHTML(item.created_at)}</small>
            </div>
        `).join("");

    } catch (error) {
        activityList.innerHTML = "<p>Unable to load activities.</p>";
    }
}
// BOOK AVAILABILITY CHART
let bookChartInstance = null;

async function loadBookChart() {
    const canvas = document.getElementById("bookChart");

    if (!canvas || typeof Chart === "undefined") return;

    try {
        const response = await fetch("/api/stats");

        if (!response.ok) {
            throw new Error("Unable to load book statistics");
        }

        const stats = await response.json();

        const available = Number(stats.available_books ?? stats.available ?? 0);
        const borrowed = Number(stats.borrowed_books ?? stats.borrowed ?? 0);

        if (bookChartInstance) {
            bookChartInstance.destroy();
        }

        bookChartInstance = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["Available Books", "Borrowed Books"],
                datasets: [{
                    data: [available, borrowed],
                    backgroundColor: ["#244b83", "#f0ad4e"],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom"
                    }
                }
            }
        });

    } catch (error) {
        console.error("Chart error:", error);
    }
}