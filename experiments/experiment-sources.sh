# ollama_model ID OLLAMA_NAME REPOSITORY REVISION GGUF_FILE MODELFILE
# REVISION may be a commit, tag, branch such as main, or latest. The special
# value latest follows the repository's default revision.
# Uncomment only the experiments you want. Review upstream license terms first.

# ollama_model qwen3-4b-2507-Q6_K exp-qwen3-4b-lmstudio-q6-k lmstudio-community/Qwen3-4B-Instruct-2507-GGUF latest Qwen3-4B-Instruct-2507-Q6_K.gguf qwen3-4b-2507.Modelfile
# ollama_model gemma4-e2b-Q4_K_XL exp-gemma4-e2b-unsloth-qat-ud-q4-k-xl unsloth/gemma-4-E2B-it-qat-GGUF latest gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf gemma4-e2b.Modelfile
# ollama_model ministral-3-8b-Q5_K_XL exp-ministral3-8b-unsloth-ud-q5-k-xl unsloth/Ministral-3-8B-Instruct-2512-GGUF latest Ministral-3-8B-Instruct-2512-UD-Q5_K_XL.gguf ministral-3-8b.Modelfile
# ollama_model gemma4-e4b-Q4_K_XL exp-gemma4-e4b-unsloth-qat-ud-q4-k-xl unsloth/gemma-4-E4B-it-qat-GGUF latest gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf gemma4-e4b.Modelfile
# ollama_model qwen35-9b-Q6_K exp-qwen35-9b-unsloth-q6-k unsloth/Qwen3.5-9B-GGUF latest Qwen3.5-9B-Q6_K.gguf qwen35-9b.Modelfile
# ollama_model qwen35-9b-uncensored-q4-Q4_K_M exp-qwen35-9b-hauhaucs-uncensored-q4-k-m HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive latest Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf qwen35-9b-uncensored-q4.Modelfile
# ollama_model qwen35-9b-uncensored-Q6_K exp-qwen35-9b-hauhaucs-uncensored-q6-k HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive latest Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K.gguf qwen35-9b-uncensored.Modelfile
# ollama_model gemma4-12b-Q4_K_XL exp-gemma4-12b-unsloth-qat-ud-q4-k-xl unsloth/gemma-4-12B-it-qat-GGUF latest gemma-4-12B-it-qat-UD-Q4_K_XL.gguf gemma4-12b.Modelfile
# ollama_model gemma4-12b-uncensored-balanced-Q4_K_M exp-gemma4-12b-hauhaucs-uncensored-q4-k-m HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced latest Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf gemma4-12b-uncensored-balanced.Modelfile
# ollama_model ornith-9b-Q5_K_M exp-ornith1-9b-deepreinforce-q5-k-m deepreinforce-ai/Ornith-1.0-9B-GGUF latest ornith-1.0-9b-Q5_K_M.gguf ornith-9b.Modelfile
# ollama_model qwable-9b-Q6_K exp-qwable9b-empero-q6-k empero-ai/Qwable-9B-Claude-Fable-5-GGUF latest Qwable-9B-Claude-Fable-5-Q6_K.gguf qwable-9b.Modelfile
# ollama_model qwythos-9b-q4-Q4_K_M exp-qwythos9b-empero-q4-k-m empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF latest Qwythos-9B-Claude-Mythos-5-1M-Q4_K_M.gguf qwythos-9b-q4.Modelfile
# ollama_model qwythos-9b-q6-Q6_K exp-qwythos9b-empero-q6-k empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF latest Qwythos-9B-Claude-Mythos-5-1M-Q6_K.gguf qwythos-9b-q6.Modelfile
# ollama_model qwen3.6-27b-Q2_K_XL exp-qwen36-27b-unsloth-ud-q2-k-xl unsloth/Qwen3.6-27B-GGUF latest Qwen3.6-27B-UD-Q2_K_XL.gguf qwen3.6-27b.Modelfile
# ollama_model gpt-oss-unsloth-ud-q4-k-xl-Q4_K_XL exp-gpt-oss20b-unsloth-ud-q4-k-xl unsloth/gpt-oss-20b-GGUF latest gpt-oss-20b-UD-Q4_K_XL.gguf gpt-oss-unsloth-ud-q4-k-xl.Modelfile
# ollama_model gpt-oss-unsloth-ud-q6-k-xl-Q6_K_XL exp-gpt-oss20b-unsloth-ud-q6-k-xl unsloth/gpt-oss-20b-GGUF latest gpt-oss-20b-UD-Q6_K_XL.gguf gpt-oss-unsloth-ud-q6-k-xl.Modelfile
# ollama_model gpt-oss-unsloth-q2-k-l-Q2_K_L exp-gpt-oss20b-unsloth-q2-k-l unsloth/gpt-oss-20b-GGUF latest gpt-oss-20b-Q2_K_L.gguf gpt-oss-unsloth-q2-k-l.Modelfile
# ollama_model gpt-oss-neo-iq4-nl-IQ4_NL exp-gpt-oss20b-davidau-neo-iq4-nl DavidAU/Openai_gpt-oss-20b-NEO-GGUF latest OpenAI-20B-NEO-IQ4_NL.gguf gpt-oss-neo-iq4-nl.Modelfile
# ollama_model gpt-oss-neo-mxfp4-moe4-MXFP4_MOE4 exp-gpt-oss20b-davidau-neo-mxfp4-moe4 DavidAU/Openai_gpt-oss-20b-NEO-GGUF latest OpenAI-20B-NEO-MXFP4_MOE4.gguf gpt-oss-neo-mxfp4-moe4.Modelfile
# ollama_model gpt-oss-heretic-codeplus-iq4-nl-IQ4_NL exp-gpt-oss20b-davidau-heretic-codeplus-iq4-nl DavidAU/OpenAi-GPT-oss-20b-HERETIC-uncensored-NEO-Imatrix-gguf latest OpenAI-20B-NEO-CODEPlus-Uncensored-IQ4_NL.gguf gpt-oss-heretic-codeplus-iq4-nl.Modelfile
