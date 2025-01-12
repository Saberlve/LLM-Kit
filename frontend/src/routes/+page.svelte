<script>
    // 定义表格数据
    let tableData = [
        {id: 1, name: "Alice", age: 25, email: "alice@example.com"},
        {id: 2, name: "Bob", age: 30, email: "bob@example.com"},
        {id: 3, name: "Charlie", age: 35, email: "charlie@example.com"},
        {id: 4, name: "David", age: 40, email: "david@example.com"},
    ];

    // 定义表格列
    const columns = [
        {key: "id", label: "ID"},
        {key: "name", label: "Name"},
        {key: "age", label: "Age"},
        {key: "email", label: "Email"},
    ];

    // 排序状态
    let sortKey = "id";
    let sortDirection = "asc";

    // 分页状态
    let currentPage = 1;
    const itemsPerPage = 2;

    // 排序函数
    function sortTable(key) {
        if (sortKey === key) {
            sortDirection = sortDirection === "asc" ? "desc" : "asc";
        } else {
            sortKey = key;
            sortDirection = "asc";
        }
        tableData.sort((a, b) => {
            if (a[sortKey] < b[sortKey]) return sortDirection === "asc" ? -1 : 1;
            if (a[sortKey] > b[sortKey]) return sortDirection === "asc" ? 1 : -1;
            return 0;
        });
    }

    // 分页数据
    $: paginatedData = tableData.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

    // 总页数
    $: totalPages = Math.ceil(tableData.length / itemsPerPage);
</script>

<style>
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        font-family: Arial, sans-serif;
    }

    th,
    td {
        padding: 12px;
        text-align: left;
        border-bottom: 1px solid #ddd;
    }

    th {
        background-color: #f4f4f4;
        font-weight: bold;
        cursor: pointer;
    }

    tr:hover {
        background-color: #f9f9f9;
    }

    .pagination {
        margin-top: 20px;
        text-align: center;
    }

    .pagination button {
        margin: 0 5px;
        padding: 5px 10px;
        cursor: pointer;
    }

    .pagination button:disabled {
        cursor: not-allowed;
        opacity: 0.6;
    }

    h1 {
        text-align: center;
        color: #333;
    }

    main {
        padding: 20px;
        max-width: 800px;
        margin: 0 auto;
    }
</style>

<main>
    <h1>Svelte Table Example</h1>

    <!-- 表格结构 -->
    <table>
        <thead>
        <tr>
            {#each columns as column}
                <th on:click={() => sortTable(column.key)}>
                    {column.label}
                    {sortKey === column.key ? (sortDirection === "asc" ? "↑" : "↓") : ""}
                </th>
            {/each}
        </tr>
        </thead>
        <tbody>
        {#each paginatedData as row}
            <tr>
                {#each columns as column}
                    <td>{row[column.key]}</td>
                {/each}
            </tr>
        {/each}
        </tbody>
    </table>

    <!-- 分页控件 -->
    <div class="pagination">
        <button on:click={() => currentPage--} disabled={currentPage === 1}>
            Previous
        </button>
        <span>Page {currentPage} of {totalPages}</span>
        <button on:click={() => currentPage++} disabled={currentPage === totalPages}>
            Next
        </button>
    </div>
</main>