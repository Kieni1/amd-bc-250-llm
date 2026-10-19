# bash completion for the supported bc250 multicall interface.
_bc250_complete() {
  local cur prev command
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]:-}"
  command="${COMP_WORDS[1]:-}"

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=( $(compgen -W 'agent-mode benchmark code code-commit compare-mtp health fetch-mtp gitea-review install maintenance model ocr ollama-profile openwebui-setup package-gate qualification rag reset resilience run-mtp status storage support-bundle verify version help --help --version' -- "$cur") )
    return 0
  fi

  case "$command" in
    qualification)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'list clean' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == list ]]; then
        COMPREPLY=( $(compgen -W '--json' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == clean ]]; then
        COMPREPLY=( $(compgen -W '--older-than-days --keep-latest --apply' -- "$cur") )
      fi
      ;;
    version)
      COMPREPLY=( $(compgen -W '--json --short' -- "$cur") )
      ;;
    status|health)
      COMPREPLY=( $(compgen -W '--json' -- "$cur") )
      ;;
    model)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'list status path install apply refresh unregister remove purge-retired' -- "$cur") )
      fi
      ;;
    benchmark)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'generation embeddings ocr task agent usecase translation rag-cycle rag-quality concurrency num-batch owui-translation owui-rag owui-embedding-batch owui-chunk-min owui-system-context' -- "$cur") )
      fi
      ;;
    rag)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'init prepare-batch review validate activate supersede status ingest' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == ingest ]]; then
        COMPREPLY=( $(compgen -W '--url --token-file --prune --timeout --allow-remote --allow-confidential-remote' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == prepare-batch ]]; then
        COMPREPLY=( $(compgen -W '--model --agent-url --max-chars --dry-run' -- "$cur") )
      fi
      ;;
    package-gate)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'capture' -- "$cur") )
      fi
      ;;
    resilience)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'start resume status' -- "$cur") )
      fi
      ;;
  esac

  case "$prev" in
    --campaign-dir|--output|--output-dir|--candidate-rpm|--source-artifact|--token-file)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
}
complete -F _bc250_complete bc250
