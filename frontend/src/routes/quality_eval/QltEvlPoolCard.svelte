<script lang="ts">
    import type PoolEntry from "../../class/PoolEntry";
    import VisbilityButton from "../components/VisbilityButton.svelte";
    import { getContext } from "svelte";
    const t: any = getContext("t");
    export let pool: PoolEntry; // Replace 'any' with the actual type of 'pool' if available
  </script>
  
  <a
    href={`/quality_eval/quality_eval_main?pool_id=${pool.id}`}
    class="block p-4 bg-white rounded-lg overflow-hidden border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-300"
  >
    <div class="flex flex-col h-full">
      <div class="mb-2">
        <h3 class="text-lg font-semibold text-blue-600 truncate">{pool.name}</h3>
        <p class="mt-2 text-gray-600 text-sm">
          {pool.description || "No description available"}
        </p>
      </div>
      
      <div class="mt-auto pt-4 border-t border-gray-100">
        <div class="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span class="text-gray-700 font-medium">ID:</span>
            <span class="text-gray-600 ml-1">{pool.id}</span>
          </div>
          <div>
            <span class="text-gray-700 font-medium">Created:</span>
            <span class="text-gray-600 ml-1">{pool.created_on}</span>
          </div>
          <div>
            <span class="text-gray-700 font-medium">Size:</span>
            <span class="text-gray-600 ml-1">{pool.size}</span>
          </div>
          <div>
            <VisbilityButton
              id={pool.id.toString()}
              asset="pool"
              interactStyle="link"
            />
          </div>
        </div>
      </div>
    </div>
  </a>