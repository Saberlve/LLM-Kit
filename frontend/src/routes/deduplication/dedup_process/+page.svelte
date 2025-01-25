<script lang="ts">
    import DeduplicationResult from "./DeduplicationResult.svelte";
    import { page } from "$app/stores";
    export let data;
    let deduplicatedEntries;
    let deletedPairs;
    deduplicatedEntries = $page?.state?.deduplicatedEntries;
    deletedPairs = $page?.state?.deletedPairs;
</script>
<DeduplicationResult deduplicatedEntries={deduplicatedEntries} deletedPairs={deletedPairs}/>