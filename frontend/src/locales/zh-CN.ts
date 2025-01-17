export default {
  root: {
    title: "LLM-Kit"
  },
  sidebar: {
    data_manager: "数据管理",
    dataset_construct: "数据集构建",
    quality_eval: "质量评估",
    dedupulication: "数据集去重",
    deployment_manager: "部署管理",
    error_log: "错误记录",
    settings: "设置",
  },
  components: {
    model_card: {
      adapters: "Adapters",
      id: "ID",
      name_and_description: "名称 & 描述",
      action: "操作",
    },
    visibility_button: {
      hide: "隐藏",
      publicize: "公开",
    },
    go_back: "返回",
    data: {
      data_pool_selector: "数据池：",
      data_pool_des: "选择数据池",
      data_set_selector: "数据集：",
      data_set_des: "从所选的数据池中选择数据集"
    },
    eval_metrics_description: {
      acc_des: "预测正确的样本数/样本数总数",
      recall_des: "基于召回率判断两个句子的相似程度",
      f1score_des: "Accuracy和Recall的调和指标",
      pre_des: "评估生成文本中与参考文本匹配的内容所占的比例",
      bleu_des: "基于准确率判断两个句子的相似程度",
      distinct_des: "反映文本生成的多样性"
    },
    device: {
      GPU_utilization: "GPU利用率：",
      memory_utilization: "显存利用率：",
    },
    deployment_params: {
      title: "部署参数",
      subtitle: "量化参数",
      subsubtitle: "量化部署参数",
      bits_and_bytes: "是否使用bits_and_bytes",
      use_flash_attention: "是否使用flash attention",
      use_deepspeed: "是否使用deepspeed",
      use_vllm: "是否使用vllm",
      description: "部署参数"
    }
  },
  fault: {
    title: "错误记录",
    description: "查看任务和进程发生错误的日志",
    message: "错误信息",
    source: "来源",
    time: "时间",
    code: "错误码",
    action: "操作",
    view_logs: "查看日志",
    download_logs: "下载日志",
    search_placeholder: "输入标签，用半角逗号分隔",
    search: "搜索",
    wordcloud: "错误词云",
    close: "关闭"
  },
  config: {
    log_out: "登出",
    model_list: "模型列表",
    title: "设置",
    description: "配置系统参数"
  },

  data:{
    title: "数据管理",
    description: "创建与管理数据池，上传数据集到数据池，支持对数据进行各种操作",
    create_pool: "创建数据池",
    no_dataset: "数据池中无数据集",
    detail: {
      title: "查看详情",
      detail: "数据池详情",
      delete: "删除此数据池",
      filter: "自动筛选",
      create_on: "创建时间：",
      size: "数据量：",
      title_1: "确认删除吗",
      p1: "确认要删除吗？",
      p2: "数据将",
      p3: "无法",
      p4: "恢复。",
      yes: "是的",
      no: "不",
      title_2: "暂存区中仍有未提交的数据",
      p5: "确认要返回吗？暂存区中仍有未提交的数据。",
      p6: "暂存区的数据将",
      p7: "不会",
      p8: "被保存。",
    },
    table:{
      col_name: "名称",
      col_time: "创建时间",
      col_size: "数据量",
      col_format: "格式",
      col_des: "描述"
    },
    delete: {
      title: "确认删除",
      data: "删除数据",
      p1: "确认要删除这个数据集吗？",
      p2: "删除后数据将不可恢复。",
      yes: "删除",
      no: "不"
    },
    uploader:{
      col_filename: "文件名",
      col_datasetname: "数据集名",
      col_des: "描述",
      col_option: "操作",
      datapool_detail: "数据池详细信息",
      zone: "暂存区",
      format: "格式",
      submit: "提交暂存区的所有文件",
      no_file: "暂存区内无已上传文件",
      enter_name: "输入数据集名称",
      enter_des: "输入数据集描述",
      move: "移出暂存区",
      click: "点击",
      or: "或",
      p1: "拖拽",
      p2: "以上传文件至暂存区"
    },
    task: {
      steps: {
        infor: "基本信息",
        upload: "上传数据",
        infor_des: "填写所创建数据池的基本信息",
        upload_des: "选择需要上传的数据"
      },
      p1: "确认已创建完成吗？暂存区中仍有未提交的数据。",
      p2: "暂存区的数据将",
      p3: "不会",
      p4: "被保存。",
      yes: "是的",
      no: "不",
      title: "创建数据池",
      description: "按照提示步骤创建数据池",
      complete: "完成",
      name: "数据池名称",
      enter_name: "请输入数据池名称",
      des: "数据池描述",
      enter_des: "请输入数据池描述"
    },
    filter:{
      title: "数据筛选",
      p1: "原始数据集：",
      p2: "保留比例：",
      name: "新数据集名称：",
      des: "新数据集描述：",
      begin: "开始筛选"
    }
  },
  deduplication: {
    title: "数据集去重",
    description: "对数据集进行去重操作以保证数据集质量",
    create_task: "Create Deduplication Task",
    task_list: "Deduplication Task List",
    task_name: "Task Name",
    task_status: "Task Status",
    task_time: "Task Time",
    action: "Action",
    view_logs: "View logs",
    download_logs: "Download logs",
    search_placeholder: "Enter the tags separated by commas",
    search: "Search",
    wordcloud: "WordCloud",
    close: "close",
    task_detail: {
      title: "Task Details",
      task_name: "Task Name",
      task_status: "Task Status",
      task_time: "Task Time",
      task_description: "Task Description",
      task_input: "Task Input",
      task_output: "Task Output",
      task_logs: "Task Logs",
      task_message: "Task Message",
      task_source: "Task Source",
      task_code: "Task Code",
      task_action: "Task Action",
      view_logs: "View logs",
      download_logs: "Download logs",
      close: "close"
    }
  }
};
