# bash completion for the supported bc250 multicall interface.
_bc250_complete() {
  local cur prev command advanced subsystem
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]:-}"
  command="${COMP_WORDS[1]:-}"

  if (( COMP_CWORD == 1 )); then
    COMPREPLY=( $(compgen -W 'advanced document health install maintenance model ocr reset status storage support-bundle verify version help --help --version' -- "$cur") )
    return 0
  fi

  case "$command" in
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
    document)
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'init prepare-batch review validate activate supersede status ingest' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == ingest ]]; then
        COMPREPLY=( $(compgen -W '--url --token-file --prune --timeout --allow-remote --allow-confidential-remote' -- "$cur") )
      elif [[ "${COMP_WORDS[2]:-}" == prepare-batch ]]; then
        COMPREPLY=( $(compgen -W '--model --agent-url --max-chars --dry-run' -- "$cur") )
      fi
      ;;
    advanced)
      advanced="${COMP_WORDS[2]:-}"
      if (( COMP_CWORD == 2 )); then
        COMPREPLY=( $(compgen -W 'agent benchmark code mtp ollama-profile openwebui qualification resilience revalidate' -- "$cur") )
        return 0
      fi
      case "$advanced" in
        agent)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'list status prepare topology enter leave normal' -- "$cur") )
          ;;
        mtp)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'list status prepare run compare' -- "$cur") )
          ;;
        code)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'run commit review' -- "$cur") )
          ;;
        qualification)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'capture list clean' -- "$cur") )
          ;;
        resilience)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'start resume status' -- "$cur") )
          ;;
        benchmark)
          (( COMP_CWORD == 3 )) && COMPREPLY=( $(compgen -W 'generation embeddings ocr task agent usecase translation rag-cycle rag-quality concurrency num-batch owui-translation owui-rag owui-embedding-batch owui-chunk-min owui-system-context parity' -- "$cur") )
          ;;
      esac
      ;;
  esac

  case "$prev" in
    --campaign-dir|--output|--output-dir|--candidate-rpm|--source-artifact|--token-file)
      COMPREPLY=( $(compgen -f -- "$cur") )
      ;;
  esac
}
complete -F _bc250_complete bc250
